find . -name '*.py' \
  -not -path '*.heroku*' \
  -not -path '*migrations*' \
| xargs flake8 --ignore E111,E114,E125,E402
