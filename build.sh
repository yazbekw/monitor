#!/bin/bash
echo "🚀 بدء عملية البناء..."
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
echo "✅ تم الانتهاء من البناء بنجاح!"
