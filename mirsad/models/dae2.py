"""DaE2: the diverse and efficient ensemble of Omolara and Alawida (2025), as reproduced here.

The paper vectorizes URLs with TF-IDF, reduces dimensions with PCA, trains several base learners
(SVM, random forest, logistic regression, decision tree, naive Bayes, KNN), and compares four
ensembles: AdaBoost, Bagging, Stacking with a logistic-regression meta-learner, and soft Voting
over KNN, logistic regression, and SVM (Table 4). Where the paper leaves a choice open, this file
makes one and says so:

- Text representation. "paper": word-level TF-IDF on the raw URL string, as Section 3.5 describes.
  "ours": character 3- to 5-grams of the canonical URL (scheme and "www." removed) hashed into
  2^20 columns, so the model cannot learn which source list a URL came from.
- PCA on sparse TF-IDF is done with truncated SVD (100 components); tree and KNN learners use those
  components plus 25 handcrafted lexical features, linear learners use the sparse TF-IDF directly.
- AdaBoost boosts depth-3 decision trees on the SVD and lexical block. The paper's best AdaBoost row
  (Table 4) boosts logistic regression; on hashed TF-IDF that variant collapsed to a constant output
  in our first runs, so we report the tree-based variant.
- KNN is fitted on a 50,000-row sample, because exact KNN over 500,000 rows is too slow to score
  live links; this is stated in the model card.
"""

from __future__ import annotations

import numpy as np
from scipy import sparse
from sklearn.base import BaseEstimator, ClassifierMixin, TransformerMixin, clone
from sklearn.calibration import CalibratedClassifierCV
from sklearn.decomposition import TruncatedSVD
from sklearn.ensemble import (AdaBoostClassifier, BaggingClassifier, RandomForestClassifier,
                              StackingClassifier, VotingClassifier)
from sklearn.feature_extraction.text import HashingVectorizer, TfidfTransformer, TfidfVectorizer
from sklearn.feature_selection import SelectKBest, chi2
from sklearn.linear_model import LogisticRegression
from sklearn.naive_bayes import ComplementNB
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVC
from sklearn.tree import DecisionTreeClassifier

from ..features.url import FEATURE_NAMES, canonical, lexical_matrix

N_SVD = 100
N_LEX = len(FEATURE_NAMES)


class URLFeaturizer(TransformerMixin, BaseEstimator):
    """Turns URL strings into one sparse matrix: [TF-IDF columns | SVD components | lexical features].

    Downstream learners pick the block they need with `Block`, so every learner in an ensemble sees
    the same rows and the featurizer runs once per fit.
    """

    def __init__(self, representation: str = "ours", n_svd: int = N_SVD, random_state: int = 42):
        self.representation = representation
        self.n_svd = n_svd
        self.random_state = random_state

    def _text(self, urls):
        return [canonical(u) for u in urls] if self.representation == "ours" else [str(u) for u in urls]

    def fit(self, urls, y=None):
        text = self._text(urls)
        if self.representation == "ours":
            self.vec_ = make_pipeline(
                HashingVectorizer(analyzer="char", ngram_range=(3, 5), n_features=2 ** 19,
                                  alternate_sign=False, norm=None, lowercase=True),
                TfidfTransformer(sublinear_tf=True))
        else:
            self.vec_ = TfidfVectorizer(token_pattern=r"[A-Za-z0-9]+", lowercase=True,
                                        max_features=100_000, sublinear_tf=True)
        tfidf = self.vec_.fit_transform(text)
        # PCA step: keep the 20,000 columns most associated with the label, then reduce them with SVD.
        # Selecting first keeps the saved SVD small (100 x 20,000) instead of 100 x 524,288.
        k = min(20_000, tfidf.shape[1])
        self.select_ = SelectKBest(chi2, k=k).fit(tfidf, y) if y is not None else None
        reduced = self.select_.transform(tfidf) if self.select_ is not None else tfidf
        self.svd_ = TruncatedSVD(n_components=self.n_svd, random_state=self.random_state).fit(reduced)
        dense = np.hstack([self.svd_.transform(reduced), lexical_matrix(urls)])
        self.scaler_ = StandardScaler().fit(dense)
        self.n_tfidf_ = tfidf.shape[1]
        return self

    def transform(self, urls):
        text = self._text(urls)
        tfidf = self.vec_.transform(text)
        reduced = self.select_.transform(tfidf) if self.select_ is not None else tfidf
        dense = self.scaler_.transform(np.hstack([self.svd_.transform(reduced), lexical_matrix(urls)]))
        return sparse.hstack([tfidf, sparse.csr_matrix(dense.astype(np.float32))], format="csr")


class Block(TransformerMixin, BaseEstimator):
    """Selects the sparse TF-IDF block ("sparse") or the dense SVD and lexical block ("dense")."""

    def __init__(self, part: str = "sparse", n_dense: int = N_SVD + N_LEX):
        self.part = part
        self.n_dense = n_dense

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        if self.part == "sparse":
            return X[:, : X.shape[1] - self.n_dense]
        return X[:, X.shape[1] - self.n_dense:].toarray()


class SubsampledKNN(ClassifierMixin, BaseEstimator):
    """KNN fitted on a stratified random sample, so scoring a live link stays fast."""

    def __init__(self, n_neighbors: int = 15, max_rows: int = 50_000, random_state: int = 42):
        self.n_neighbors = n_neighbors
        self.max_rows = max_rows
        self.random_state = random_state

    def fit(self, X, y):
        y = np.asarray(y)
        rng = np.random.default_rng(self.random_state)
        idx = np.arange(len(y))
        if len(y) > self.max_rows:
            idx = rng.choice(idx, self.max_rows, replace=False)
        self.knn_ = KNeighborsClassifier(n_neighbors=self.n_neighbors, weights="distance", n_jobs=-1)
        self.knn_.fit(X[idx], y[idx])
        self.classes_ = self.knn_.classes_
        return self

    def predict_proba(self, X):
        return self.knn_.predict_proba(X)

    def predict(self, X):
        return self.knn_.predict(X)


def _sparse(model):
    return make_pipeline(Block("sparse"), model)


def _dense(model):
    return make_pipeline(Block("dense"), model)


def _lr():
    return LogisticRegression(C=4.0, solver="liblinear", max_iter=300)


def _svm():
    return CalibratedClassifierCV(LinearSVC(C=0.5), cv=3, method="sigmoid")


def build(ensemble: str, representation: str = "ours", random_state: int = 42) -> Pipeline:
    """One of the four DaE2 ensembles as a pipeline that takes raw URL strings."""
    if ensemble == "adaboost":
        # Boosting logistic regression on the hashed TF-IDF (the paper's best AdaBoost row) collapsed to a
        # constant output in our runs, so AdaBoost boosts shallow trees on the SVD and lexical block.
        clf = _dense(AdaBoostClassifier(estimator=DecisionTreeClassifier(max_depth=3), n_estimators=150,
                                        learning_rate=0.5, random_state=random_state))
    elif ensemble == "bagging":
        clf = _dense(BaggingClassifier(estimator=DecisionTreeClassifier(max_depth=22, min_samples_leaf=2),
                                       n_estimators=30, max_samples=0.5, n_jobs=-1,
                                       random_state=random_state))
    elif ensemble == "stacking":
        clf = StackingClassifier(
            estimators=[
                ("lr", _sparse(_lr())),
                ("nb", _sparse(ComplementNB(alpha=0.3))),
                ("svm", _sparse(_svm())),
                ("rf", _dense(RandomForestClassifier(n_estimators=60, max_depth=24, n_jobs=-1,
                                                     random_state=random_state))),
                ("dt", _dense(DecisionTreeClassifier(max_depth=18, random_state=random_state))),
            ],
            final_estimator=LogisticRegression(max_iter=500), cv=3, stack_method="predict_proba")
    elif ensemble == "voting":
        clf = VotingClassifier(
            estimators=[("knn", _dense(SubsampledKNN(random_state=random_state))),
                        ("lr", _sparse(_lr())),
                        ("svm", _sparse(_svm()))],
            voting="soft")
    else:
        raise ValueError(f"unknown ensemble {ensemble!r}")
    return Pipeline([("features", URLFeaturizer(representation, random_state=random_state)), ("model", clf)])


ENSEMBLES = ("adaboost", "bagging", "stacking", "voting")


def for_live_scoring(model):
    """Switch every fitted estimator to one thread.

    Training uses all cores (n_jobs=-1). For one link at a time, starting a pool of workers costs far
    more than the prediction, so live scoring runs single-threaded.
    """
    seen = set()

    def walk(obj):
        if id(obj) in seen:
            return
        seen.add(id(obj))
        if isinstance(obj, BaseEstimator):
            if hasattr(obj, "n_jobs"):
                obj.n_jobs = 1
            for v in vars(obj).values():
                walk(v)
        elif isinstance(obj, (list, tuple)):
            for v in obj:
                walk(v)
        elif isinstance(obj, dict):
            for v in obj.values():
                walk(v)

    walk(model)
    return model


class DaE2(ClassifierMixin, BaseEstimator):
    """All four ensembles sharing one featurizer; scores are each ensemble's probability and their mean.

    Training the featurizer once and the four models on its output is what makes scoring cheap
    enough for live links: one vectorization, four predictions.
    """

    def __init__(self, representation: str = "ours", random_state: int = 42):
        self.representation = representation
        self.random_state = random_state

    def fit(self, urls, y):
        # y is passed so the chi-squared selection runs before the SVD (without it the SVD would span
        # all 524,288 hashed columns: a 500 MB model and seconds per URL).
        self.features_ = URLFeaturizer(self.representation, random_state=self.random_state).fit(urls, y)
        X = self.features_.transform(urls)
        self.models_ = {}
        for name in ENSEMBLES:
            model = clone(build(name, self.representation, self.random_state).named_steps["model"])
            self.models_[name] = model.fit(X, y)
        self.classes_ = self.models_["adaboost"].classes_
        return self

    def votes(self, urls) -> dict[str, np.ndarray]:
        X = self.features_.transform(urls)
        pos = list(self.classes_).index(1)
        return {n: m.predict_proba(X)[:, pos] for n, m in self.models_.items()}

    def predict_proba(self, urls):
        v = self.votes(urls)
        p = np.mean(np.vstack(list(v.values())), axis=0)
        return np.vstack([1 - p, p]).T

    def predict(self, urls, threshold: float = 0.5):
        return (self.predict_proba(urls)[:, 1] >= threshold).astype(int)
