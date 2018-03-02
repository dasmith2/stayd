find . -name '*.py' \
  -not -path '*.heroku*' \
  -not -path '*migrations*' \
| xargs flake8 --ignore E111,E125
