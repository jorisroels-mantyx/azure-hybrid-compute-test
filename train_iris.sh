#!/usr/bin/env bash
# Iris classification training script.
# Runs on the on-prem node via Arc Run Command.
# Uses uv to create an isolated venv — no system-wide installs needed.

set -euo pipefail

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

echo "==> Node: $(hostname)  |  $(date)"
echo "==> Setting up Python environment..."

echo "==> Installing uv..."
curl -fsSL https://astral.sh/uv/install.sh | UV_INSTALL_DIR="$WORKDIR" sh
UV="$WORKDIR/uv"

"$UV" venv "$WORKDIR/venv" --quiet
"$UV" pip install --quiet --python "$WORKDIR/venv/bin/python" scikit-learn

echo "==> Training iris classifier..."
"$WORKDIR/venv/bin/python" - <<'PYEOF'
from sklearn.datasets import load_iris
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.metrics import classification_report
import numpy as np

X, y = load_iris(return_X_y=True)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

clf = RandomForestClassifier(n_estimators=100, random_state=42)
clf.fit(X_train, y_train)

cv_scores = cross_val_score(clf, X, y, cv=5)
print(f"Cross-validation accuracy: {cv_scores.mean():.4f} (+/- {cv_scores.std():.4f})")
print(f"Test accuracy:             {clf.score(X_test, y_test):.4f}")
print()
print("Classification report:")
print(classification_report(y_test, clf.predict(X_test),
      target_names=load_iris().target_names))
PYEOF

echo "==> Done."
