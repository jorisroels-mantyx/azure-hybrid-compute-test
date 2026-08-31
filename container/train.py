import os

from sklearn.datasets import load_iris
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report
from sklearn.model_selection import cross_val_score, train_test_split

n_estimators = int(os.getenv("N_ESTIMATORS", "100"))

X, y = load_iris(return_X_y=True)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

clf = RandomForestClassifier(n_estimators=n_estimators, random_state=42)
clf.fit(X_train, y_train)

cv_scores = cross_val_score(clf, X, y, cv=5)
print(f"CV accuracy: {cv_scores.mean():.4f} ± {cv_scores.std():.4f}")
print(f"Test accuracy: {clf.score(X_test, y_test):.4f}")
print()
print(classification_report(y_test, clf.predict(X_test), target_names=load_iris().target_names))
