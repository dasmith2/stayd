find . -name '*.py' | xargs flake8 --ignore E111 --exclude=*/migrations/*
