# Someday I'll figure out how to run this as part of heroku's ci.
# sudo apt-get install nodejs
# sudo apt-get install npm
# sudo npm install -g jshint
# sudo ln -s /usr/bin/nodejs /usr/bin/node
jshint --config=./jshintrc static/js/*
