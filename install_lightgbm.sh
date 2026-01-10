#!/bin/bash
set -e
echo "=== Installing LightGBM ==="
/Users/chengtang/Desktop/Crypto_Alpha_Terminal/crypto_alpha_terminal/bin/pip install lightgbm
echo "=== Testing LightGBM Import ==="
/Users/chengtang/Desktop/Crypto_Alpha_Terminal/crypto_alpha_terminal/bin/python3 -c "from lightgbm import LGBMClassifier; print('SUCCESS: LightGBM loaded!')"
