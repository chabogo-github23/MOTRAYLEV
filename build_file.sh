

#!/bin/bash

# Install dependencies
pip install -r requirements.txt

# Collect static files
python manage.py collectstatic --noinput

# Create staticfiles_build directory if it doesn't exist
mkdir -p staticfiles_build

# Copy static files to staticfiles_build
cp -r staticfiles/* staticfiles_build/ 2>/dev/null || :
