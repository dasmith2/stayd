# Howard!

Welcome to Howard! (formerly, Stayd!)

## Get permission to things

Get a Github account and get yourself added as a contributor to
https://github.com/githubstayd/stayd-web

Get a Heroku account and get yourself invited as a member to the
stayd-developers team on
https://dashboard.heroku.com/teams/stayd-developers/overview

Get yourself added to the heroku-errors@stayd.com Google group on
https://admin.google.com/AdminHome#GroupDetails:groupEmail=heroku-errors%2540stayd.com

## Running Locally

You'll need the code.

    git clone git@github.com:githubstayd/stayd-web.git

You'll need posgresql.

    sudo apt-get update
    sudo apt-get install postgresql postgresql-contrib
    # The -W here forces a prompt for a password.
    sudo -u postgres createuser --interactive -W
    Enter name of role to add: dave2
    Shall the new role be a superuser? (y/n) y
    Password: asdf1234
    sudo -u postgres psql
    create database staydweb

Uh, using -W to force a password prompt either didn't work or I made
a typo. Anyway you can also do it thusly:

    sudo -u postgres psql
    \password dave2

Now go put this in stayd/local_settings.py

    DATABASES = {
      'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': 'staydweb',
        'USER': 'dave2',
        'PASSWORD': 'asdf1234',
        'HOST': 'localhost',
        'PORT': ''
      }
    }

You'll need Python 3.6. If you're on Ubuntu 16.04...

    sudo add-apt-repository ppa:deadsnakes/ppa
    sudo apt-get update
    sudo apt-get install python3.6

You'll need pipenv.

    sudo apt-get install python-pip
    pip install pipenv
    cd ~/stayd-web
    pipenv --python /usr/bin/python3.6
    pipenv install
    pipenv shell # You run this one every time.

Or you can put some shortcuts in your ~/.bashrc or whatever. I got

    alias cd_stayd='cd /home/dave/stayd-web'
    alias stayd='cd_stayd; pipenv shell'
    alias gitt='eval "$(ssh-agent -s)"; ssh-add ~/.ssh/id_rsa'
    alias staydd='gitt; stayd'

You'll need this extra package in dev but it shouldn't get checked into
the pipfile, so use pip to install it.

    pip install django-debug-toolbar

Now you can do all kinds of rad things, such as

    ./manage.py migrate
    ./manage.py test
    ./manage.py runserver

    ./manage.py shell
    from guesty.guesty import sync_all_reservations
    from datetime import date
    sync_all_reservations(from_date=date(2018, 9, 1), to_date=date(2018, 10, 1))

Here's how to run the web tests.

    pip install selenium
    Go get the latest geckodriver here:
    https://github.com/mozilla/geckodriver/releases
    Extract it, and get it in your path. I just did something like
    sudo mv /home/dave/Downloads/geckodriver /usr/bin
    ./manage.py web_tests

## Heroku

The websites run on Heroku.

Install the Heroku CLI.

    sudo snap install heroku --classic

Once you run these commands...

    cd stayd-web
    heroku git:remote -a stayd-prod
    heroku git:remote -a stayd-stage

You'll be able to do things like

    heroku run python manage.py shell -a stayd-prod
    heroku run python manage.py dbshell -a stayd-stage
    heroku run bash
    heroku logs -t -a stayd-prod -d web
    heroku logs -t -a stayd-prod -d worker
    heroku logs -t -a stayd-prod -d clock
    heroku domains:add verifyid.hihoward.com -a stayd-prod

## Adding domains

That domains:add command will return something like

    Adding verifyid.hihoward.com to ⬢ stayd-prod... done
     ▸    Configure your app's DNS provider to point to the DNS Target
     ▸    hidden-mackerel-3bbdddwc4jihshjgt0r1zg1s.herokudns.com.
     ▸    For help, see https://devcenter.heroku.com/articles/custom-domains

    The domain verifyid.hihoward.com has been enqueued for addition
     ▸    Run heroku domains:wait 'verifyid.hihoward.com' to wait for completion

To finish wiring that up, go to https://my.1and1.com/Dashboard

Domains and SSL -> hihoward.com (NOT hihoward.co haha) -> Subdomains

Add your new subdomain, in this case verifyid

Then click on your subdomain -> DNS (along the upper bar). Click "Add record".
Click CNAME. In this case,

    Host name verifyid
    Points to hidden-mackerel-3bbdddwc4jihshjgt0r1zg1s.herokudns.com

Note there's no . at the end of `Points to`. Heroku included precisely the most
confusing punctuation in their response to the domains:add command.

ionos.com then gives you a terribly alarming sounding confirmation screen. "The
service will be disabled". It's fine. Click Save. Your subdomain is finally
hooked up!

## Deploying

Well for starters, don't deploy on Friday unless you want to work on Saturday.
Don't deploy past 3pm unless you want to work past 8pm.

Do yourself a favor, and run a few checks locally to save time.

    ./lint.sh
    ./manage.py test

Then push...

    git push

Then Heroku should take care of all the steps to deploy to stage. Once it's on
stage you can click a button on
https://dashboard.heroku.com/pipelines/2f32892f-a3a5-4993-8d07-94feda2dd7fc to
push it to prod. You can see in Procfile that database migrations happen as
part of the deploy process.

## cron scheduling

See extensive comments in clock.py

## emails

Guest emails are sent through a totally different pathway than notificiations
to internal staff, which is good, because staff emails started ending up in
spam folders a long time ago.

Guest emails go through Mandrill and are sent from the hihowardmail.com domain
at the time I wrote this.

Error emails and all manner of internal notification emails go through Mailgun
via a totally different domain, hihowardstaffmail.com, technically the
mg.hihowardstaffmail.com subdomain. To configure Mailgun, go to stayd-prod's
heroku page and click on "Mailgun" under "Installed add-ons".

To configure DNS, go to
https://my.ionos.com/domain-dns-settings/hihowardstaffmail.com

## The enjoyment of pair programming

I love pair programming. Do that every day, but only with people you enjoy pair
programming with. I don't want people scheduling meetings to talk about work. I
want people working, and I want them working together. Lead by doing. For
starters, now you're in tune with one another. Now you're doing teamwork, and a
good team is more than the sum of its parts. It's the easiest thing in the
world to get hung up on some wacky problem for hours and hours. But somebody
who knows what they're doing can get past it in moments. THAT'S what I call
leadership. Getting people through roadblocks. That's very helpful. You know
what isn't helpful? Sitting in a meeting with a manager who's forgotten how to
code. That's useless at best. Pair programming is great for focus too because
you can't check Facebook while you're working with somebody. In a pair
programming session with somebody who doesn't know what they're doing, lots of
learning is happening. They should be the ones typing by the way. In a pair
programming session with somebody who knows what they're doing, lots is getting
done.

Now, I don't know about you, but I'm sensitive about not knowing things. I
don't want to bother anybody and I don't want to feel stupid. So I think it's
best if the folks who are feeling very confident and productive are the ones
pleasantly reaching out to whoever they suspect could use a pair programming
buddy. But if you find yourself stuck on problems, you could use help, and I
encourage you to go find it for yourself. If we have a culture of everybody
pair programming every day, then this won't be a problem.

Pair programming is also exhausting. That's part of the reason there's no
mandatory work schedule and it's important you have a fulfilling and
rejuvinating home life.

Please grab a pair programmer before doing anything risky, such as directly
modifying production data in a shell.

Last but not least, pair programming is a defensive strategy against some of
the more insideous corporate dynamics you typically see. As businesses grow,
you necessarily get a hierarchy, and folks naturally want to climb that
hierarchy. But, to be frank, there's not much to DO at the top. Nevertheless,
you need to SEEM important. So you tend to see the usual suspects of dubious
initiatives forced down the chain by well-meaning execs trying to demonstrate
how rad they are. To my mind, the classic example is along the lines of,
"measure" the immeasurable, then yell at people who "measured" bad and give
raises to people who "measured" good. But how are you going to measure software
development (or any other insight work), and how are you going to rank
individuals when a team is more than the sum of its parts? It's like, stack
rank the ingedients of this cake. To my mind, the POINT of formal performance
reviews is to give a veneer of numerical respectability to the prejudice that's
happening anyway. Well, that's bad because it divides the team. It singles
people out and puts them on the defensive, exacerbating the situation. It
frames the situation unhelpfully too, like, the PERSON is bad so let's not
bother to look at the circumstances or get creative about finding a niche for
them. Pair programming spreads credit and makes it hard to single anybody out,
like a phalanx or something.

So really, there's a connected graph of the people who enjoy pair programming
together, and it's that graph that creates value for business. The enjoyment of
pair programming is the foundation of my team. I keep saying "enjoyment"
because good moral is essential to self motivation. In order for somebody to
get fired, they must first become isolated from the team because nobody enjoys
pair programming with them.

## My productivity hypothesis

When it comes to productivity, reusable code is the single most important
factor. Good abstractions are reusable. You can sense how good your
abstractions are, how reusable your code is, based on how easy it is to develop
new features.

If you find that a new feature is confusing and painful to implement, then you
typically have two choices. You can either modify the existing abstractions to
make them reusable, or you can just write a bunch of new code.

Fixing existing abstractions requires a spiritual mindset. You have to sleep on
it. You often have to do some rather awkward and difficult work. Perhaps you
realize that, ideally, there would be a base class for a model that's got a
bunch of production data already. That's hard. And when you're done splitting
your model into base and child classes, you haven't actually built anything new
yet. So you have to be patient. You probably have to think a lot. You don't
really write that much code. But the code you do write is easy to reuse. Code
per feature is low because code reuse is high. It's like, you got less code,
but what you do have is multiplied by itself. 10 * 10 is 100.

The alternative is just banging out a bunch of new code that does what you
want. You probably don't have to think as much because the work is
straightforward. It's easy to create new tables. It's easy to just copy paste
the parts you need. But existing poor abstractions remain, and new ones are
introduced on top of them. Now, code required per feature is high because code
reuse is low. You banged out a lot of code quick, so there's lots of code,
but what you have is only added to itself. 20 + 20 = 40.

Which mindset should you rock in real life? Well, it depends on your
incentives. If you're under a lot of pressure to deliver in the short term, or
if you're mind isn't working well because you've been grinding out long weeks,
or if you'd like to demonstrate an impressive amount of activity for your
upcoming performance review, honestly you'd probably want to bang out new code!
Welcome to Google. There's a reason they have tens of thousands of engineers
and, I suspect, the largest code base in history.

If what you want is more features in the long run, pressuring engineers is
precisely the wrong strategy. You'll get more effort, you'll get more code,
sure, but you'll accomplish less per engineer. In programming, insight counts
more than effort, and it's hard to wait patiently for insight when you're under
pressure.

So. In the interests of productivity, my idea is to create an environment that
reduces pressure and encourages long term thinking. For instance, I don't
believe in dreadlines. a.k.a. totally arbitrary timelines nobody believe in.
Now there's no excuse to let confusing, non-reusable code stand. So the team
takes that time to de-confuse and reuse the code.

Step one. Identify the things that confuse you. Step two. Fix them. Step three.
Envision a solution in your head. Only then do you move on to step 4: write new
code. Don't write new stuff while you're still confused. You'll only add to the
confusion. Whatever you do, don't just poke around changing things at random
and seeing if that happens to fix the problems.

Tom independently arrived at a similar conclusion while onboarding dozens of
new units at once. It's a complicated job with a lot of details. If, by moving
10% slower, you can be more organized as you go, then you'll get the whole job
done much faster.

Code has to make sense in tests, it has to make sense in the deployed server
itself, and it has to be helpful when you're working in the shell. Good code is
clear and useful in all three contexts. A somewhat surprising thing here is,
the shell loves standalone functions! It's not necessarily always the best move
to collect all your functions in objects. It's definitely not necessarily the
best move to get excited about some shiney framework that requires you to spend
months refactoring your code for rather vague, abstract promised benefits. I'm
suspicious of frameworks. I love useful libraries.

There are specific reasons you might need an object, such as needing something
to mock for tests. The naive form of encapsulation is to put everything in
objects and/or frameworks or whatever. The harder and way more useful form of
encapsulation is more like, ok, something comes up. Imagine where the single
obvious place to fix it SHOULD be. If that place doesn't exist (and there isn't
a better idea lying around) create it. A really important concept here is,
which modules know about which modules?

The temptation to let bad code remain is strong, especially for less
experienced developers who are afraid of screwing everything up. So bravery and
confidence (and tests) are important here.

I guess, if you got good abstractions that's not quite enough. You need focus
too. You know what's vital for focus? Projects that don't suck. Nobody can stay
focussed when the work sucks.

Also work life balance is essential for focus. You can't focus while you're
hung over or exhausted or whatever. Among the chief elements of productivity
are such diverse elements as good abstractions, focus, insight, good
requirements... I'll come in again.

## The code is a non-cyclical directed graph with minimal edges

These things tend to show up at the same time:
1. A module knows too much.
2. There are 2 possible places to fix a problem.
3. The code is confusing.
4. There's a circular dependency.
5. A code file is getting really big.

In a circular dependency, A depends on B, and B depends on A. Maybe the Message
module has some basic concepts. A Message has content, a recipient, a method of
delivery, stuff like that. Then there's a, I don't know, Sprocket module which
wants to send a message whenever a new Sprocket is available. So Sprocket
defines SprocketMessage which inherits from Message. So far so good. A depends
on B.

A new requirement comes up! Somebody wants a daily summary of all messages. You
think you'd put that right in the Message module. Makes sense, right? It
applies to all Message types so it's kind of abstract, just like the Message
module. So you define DailyMessage in the Message module and start sending out
a daily list of messages. And for a time, everyone is happy.

But then the person who reads the DailyMessage wants to know, only in the case
of SprocketMessages, what the delay was between creation of the Sprocket and
sending of the message. So now DailyMessage needs to know Sprocket details. So
now Message has to import Sprocket and probably SprocketMessage and boom,
circular dependency. Now the code won't even run without a hack like putting
your imports directly in a function or something.

The fundamental problem is that you have basic definitions and advanced high
level stuff in the same module. Message should stay simple and import basically
nothing. All it knows is the most basic definition of a message. Sprocket knows
about Message. There's no getting around that. Now you create a THIRD MODULE
DailyMessage which knows about Message and Sprocket. Now your code runs and
makes sense.

But our troubles aren't over yet. A new requirement comes up! Somebody wants
DailyMessage to describe the reason each message was sent. Where does this new
"reason" field and logic go?  You might think since only DailyMessage cares
about the reason, DailyMessage should be responsible for storing and describing
the reason. But that's confusing. If you want to know why a SprocketMessage
sent, I expect to open the Sprocket module, not the DailyMessage module. In
addition, if somebody adds a new type of BlarghMessage or whatever, they know
to pay attention to the Message module obviously, but it's NOT obvious that
they also need to pop on over to DailyMessage and describe the reason for a
BlarghMessage. You probably won't discover this oversight until the first
BlarghMessage gets created in production and DailyMessage breaks at 7pm on
Friday because it has no idea what a BlarghMessage is or why it was sent.
Here's another problem.  Years go by and we have 50 types of messages. Now
DailyMessage is a monolith.  It's got over 50 imports, one for each type of
message. It has to describe the reason behind each of them, probably in a
function that's about a thousand lines long. What a mess.

So here's what you do. Put the reason field in Message, the most basic spot.
Make it required. But DON'T put any logic in Message that populates or uses the
field. All Message knows is that SOMEBODY is responsible to populate that field
because SOMEBODY needs to use it. This makes it the responsibility of the
specific type of Mesage to describe its reason. So SprocketMessage describes
why SprocketMessages get sent. Now when you add BlarghMessage and forget to
describe the reason, it'll blow up the moment you try to create a
BlarghMessage, but luckily DailyMessage is unaffected.

Now every bit of Sprocket logic is in the Sprocket module, the DailyMessage
object is confident it can describe why every message was sent, and the Message
module remained simple. There's no ghastly list of 50 imports even though there
are 50 types of Message. The code is a non-cyclical directed graph, and it
makes sense. Whatever change you can imagine making, there's 1 obvious spot to
go.

One last point. You know how we put the abstract "reason" concept in the
Message class and every single type of Message had to describe the reason? Well
what about that Sprocket delay requirement. Should every single type of Message
have to describe some kind of abstract delay concept, even though
SprocketMessages are the only type of Message where the concept of a delay even
makes sense? Nah. That's too much abstraction. That's the blind application of
a pattern, and it will cause a bunch of useless boilerplate. In a way, it's
kind of the opposite problem from what we had originally. Instead of a circular
dependency monolith type situation, we got a splintered useless code situation.
Here's all you have to do. SprocketMessage describes its delay. DailyMessage
has just 2 imports: Message and SprocketMessage, and in the case of
SprocketMessages, it also includes a description of the delay.

## Productivity no wait this is more important

When I look back over wasted time on projects, I feel like a lot of that was
confused, incorrect, or absent requirements.

When you have no requirements, you end up designing the user experience and the
business rules as you program. This makes for slow going, as it's quite the
chore to contemplate all that AND code at the same time.

Confused requirements are hard to program off of, because if the requirements
literally make no sense, how is your code supposed to make any sense.

You can move fast enough with incorrect requirements, but then when you realize
your mistake it's, like, you spent 2 days building the wrong thing, 1 day
un-building the wrong thing, and 3 days building the right thing.

## No useless code

All code is a liability. Code clutters up files and makes them hard to read.
Code tends to break over time. Minimize liability by minimizing code. Ah, but
don't be so naive as to simply count lines of code. Sometimes you can write
real magical code that's 10% fewer lines, but 100% more confusing.

If a feature isn't actually being used, it ought to be revisited, and either
put into use or thrown out. If you suspect a feature isn't being used, throw a
log_error call in there to alert us if it actually is being used.

I don't care how much work went into a feature. If it doesn't reflect reality,
if it's wrong, then it needs to be fixed or thrown out. The REALLY important
artifacts aren't code, they're learned lessons.

Don't make placeholders. Don't build it until we need it (spoiler alert: you
won't). Don't keep bad code for the sake of anybody's ego.

Ok ok, sometimes it's just so hard to let go. That's what the scrap_heap
app is for. Put your code in there if you can't bear to let it disappear.

## Build it and they will come, vs Build it because they're already here

Build it and they will come is, like, a solution looking for a problem. In my
experience, the success rate of this style of project is real low. Often,
these projects are waterfalls. You conceive of a whole big vision, build the
whole thing, then see if it attracts a lot of human attention and use.
Typically, it doesn't. And even if it does, many features are dead weight and
many are dead wrong but are too much work to fix.

I love this company because the guests are already here. The problems are
pretty obvious. You can accomplish a lot with a 2 week project in an
environment like that. You can solve a real problem. Your code goes into
immediate use, the team is happy, and the company improves. My idea is to just
act like that, writing actually useful code for years until you've got ten
thousand useful features and everybody's jobs are going as smoothly as
possible. THEN you take a step back and appreciate the big picture. The only
way to complete a great unknown journey is step by step, correcting as you go.
If you're doing something new, you CAN'T know what steps you'll take 6 months
from now.

But. There are (and will always be) folks on the team who are a little
impatient for that. Their dreams are all build-it-and-they-will-come.
Typically, these team members are preoccupied with looking impressive to
investors. They feel that letting the projects define themselves is
"reactionary" or something. They feel bad that they aren't leveraging their
considerable genius to conceive of huge impressive forward thinking waterfall
projects.

The reality of trying to get a good project out of somebody who's thinking in
this way is pretty frustrating. They don't really know what they want because
they aren't solving real problems. They're trying to predict the future and
naturally they have some trouble clarifying that.

You could try to interpret their vague ideas and build something, anything,
that COULD be what they're talking about. But this is a naive strategy. They
won't be happy with the end result, and your code will fall into immediate
disuse.

My strategy for that dynamic is basically to keep them pinned down with
homework. I'm looking for something, anything, they're confused about. Then
I ask them to figure that part out. They're usually totally relieved to have a
good excuse to go work on their own. And if they do manage to figure a whole
project out, cool cool, now their project competes with all the other projects
at the monthly prioritization meeting. And if they manage to get their project
prioritized there, much to my surprise, well then it's actually a good project
and I'm happy to do it! More likely though, they'll never get that project
defined. And they might feel a little bad that they never communicated some
grand vision to you, but hopefully they don't feel THAT bad because you've been
working on useful stuff the whole time. They can talk to you about how they're
looking foward to a more visionary phase of software development or something,
and you can be totally supportive of that.

The beauty of this strategy is, it's all good vibes. You're encouraging the
whole time, yes-and-ing people. But it also protects you from pointless
projects.

## Stakeholders

I don't like layers of misdirection between software engineers and the people
who actually use the software. If Jane uses the software every day, an engineer
who is in a position to do something should ask her what her frustrations are,
and fix them. Otherwise you leave a lot of low hanging fruit unpicked. If you
aren't listening to stakeholders, you're probably listening to a project
manager who's only theorizing about what the stakeholders need AND doesn't know
how to program and therefore know what the easy obvious wins are.

Every request for information is really a request for a feature, some kind of
easy way to look that information up going forward.

## APIs

We tried for a while to get access to Airbnb data directly. Then I tried
building scrapers, and that was an unsustainable nightmare. The breakthrough
happened when McKay put in a heroic effort evaluating, like, Channel Managers.
They were varying degrees of awful, but in the end we went with Guesty, and
despite dozens of bugs we were never totally blocked. Once I had a pipeline of
data from Airbnb to Guesty to our database, I could finally start kicking out
features like reports and guest messaging. And, we could hook up to new
channels pretty easy.

The lesson I took from that was, look, for every kind of need we've got,
maybe somebody out there is trying to make money solving that. And for $50 a
month or whatever you can sidestep a whole maintainability nightmare.

Although now that we've been through Properly, I can appreciate the flipside:
sometimes trying to use somebody else's features is a maintainability
nightmare, especially since now you aren't in a position to fix problems. So I
don't know. Sometimes it's about taking control of your core workflows and
tailoring them equisitly.

Anyway, I guess my point is this project has a lot to do with hooking up to one
API after another. Properly, Bento, Xero, Stripe, Front, Aircall,
Mailchimp/Mandrill, Guesty, and S3 at the time I'm writing this. This project
is gluing in new things, writing the cement between the bricks, you know?
Someday I could see it making sense to enter a clone stage where we build all
this stuff ourselves.  We're doing that now for Properly. But stay humble and
let bought software do the work if it's a good fit.

I think an important principle is, these APIs, there are a lot of them and this
could get really complicated. We're liable to replace Guesty some day, or at
least use an additional Channel manager but for hotels, or something. So it's
a bad idea to have a bunch of Django apps (by that I just mean subfolders
in stayd-web) with scattered references to Guesty. That would be a) confusing
b) hard to maintain and c) unswappable. The image I have in my mind is, at the
center we've got the reservations, rentals, guests, and expenses apps. These
should know as little as possible about any API we're hooked up to. The APIs we
hook up to should put things in those packages, and take things out of those
packages. API packages shouldn't reference other API packages for the most
part. The guesty app should pull data from guesty, put it in reservations, and
then the stats package should pull things out of the reservations package.
stats should have no clue that Guesty even exists. It's like the spokes on a
bike. Signals are an important tool here. The downside to sending a signal is
that you can't get a return value. But the upside is that the app sending the
signal can remain totally ignorant of whoever receives the signal.

I've gotten this wrong so many times, here's what I've settled on. Apps have an
api.py file that know how to make api calls, but aren't aware of business
logic. APIs raise ServerError when they encounter 500s and such, and
NotOkErrors when the API completes a response successfully but has some kind of
error message in it. APIs return data, not responses. Write code that uses that
data. Then when the API has specific problems we didn't anticipate, it throws
specific exceptions we don't catch, and we get emails. Then we program specific
solutions around each specific problem we enounter until we stop getting
emails. Please don't program overly-broad, catch-all type fixes because you'll
end up swallowing errors. api.py files handle rate limiting by waiting and
retrying requests. Never make a call to an api in a web thread.  Enforce this
with calls to can_write_net and can_read_net. These are beautiful ideas that
are definitely not consistent across keys yet!

## Tables and performance

Keys is basically a glorified spreadsheet. Stay humble. We ought to be really
good at displaying tables and making them available for CSV download. Use the
util.table classes for html and csv rendering.

No page should ever take more than half a second or so to load. Hah.

Now, it's the easiest thing in the world to code up a table that runs SQL
queries per row. But the team is always pulling back, like, "ALL the rows from
2018!!" and then downloading it as a CSV. If each row causes sql queries, you
very quickly end up with hundreds if not thousands of sql round trips on a
page, and the page starts hitting the 30 second timeout. That's called,
"Grinding to a halt."

You might be tempted to use caching. But caching is a sure fire source of
errors, especially when it's deployed simply to avoid dealing with underlying
performance issues. A lazy-load cache unpredictably causes slow requests
whenever it has to regenerate the page, which just makes your problems
nondeterministic. We got a nice fast database, so whenever possible we should
use insight and well structured code instead.

At one point, the "Pay service providers" table ground to a halt. But at the
end of the day, it's making one row per payment. It's not a fundamentally
difficult problem, just a complicated one with lots of details. Now it pulls
everything it needs with a single query, and the page loads quick-snap. It
accomplishes this through select_related, a simple but powerful feature of the
Django ORM. See get_pay_service_provider_payments

(Note: this strategy isn't keeping up with the pay service providers page!)

The stats package is a cache, but it's a thoughtfully designed one that solves
a fundamentally difficult problem. We've got tons of reservations, each with
payments and line items, tons of expenses and such, and we want to see
aggregate numbers per day and per month. This isn't a, "We're just making one
row per row," problem here you could solve with select_related. I can't imagine
a fast, maintainable way to pull back a table of amortized stats by day using
a single SQL query. There's so much business logic involved. The stats package
is a cache, absolutely. But it's a well programmed cache that's always up to
date, fast, reasonably well-typed, minimally denormalized, and well tested.
I surprise myself with how fast I can develop new features in it, which tells
me it's well abstracted.

## Background threads

You know what else can make a request take too long? API calls. After all, they
have to execute an entire http request, plus who knows how well that API is
programmed.

So API calls should all be made on the background thread. But it's possible for
our Reddis queue to get a connection error, or a data migration happened
between when a task was enqueued and executed so it's no longer valid,
whatever. So, create a function that does what you need. Kick off the job right
away, but also, there should be some kind of periodic catch up mechanism,
kicked off by clock.py that just circles back around and makes sure there are
no dangling tasks.

## Keeping it simple, technology-wise

I've worked with relational databases and NoSQL architectures, and I have to
say. Good old fashioned databases are just easier. There's a reservations
table. Each reservation is exactly one row in that table, end of story. In
NoSQL, you end up with O(use cases) copies, and THE classic bug is those copies
getting out of sync with one another. You really do need a lot more code and a
lot more engineers to accomplish the same features.

Really the single only important intrinsic limitation of a database is, you
can't scale it infinitely. If we actually do need infinite scale because we get
so successful, that's a good problem to have. Strategically, the way to do it
if you ask me is to use the easier to modify system as long as possible,
constantly updating it to be accurate and simple, and then when you're forced
to scale you have an excellent spec to base it off of. The more accurate your
spec, the less time you spend fixing, which gets really important in NoSQL
architectures.

I've worked with websites and (Android) apps, and I have to say. Good old
fashioned websites are just easier. You can deploy a new version and everybody
uses it automatically. You can write Selenium tests.

Really the single important limitation of websites is, you need to be online.
But we have internet in all our units, plus people are just online on their
smart phones these days. So I think we can get away with this.

## Testing

Most of the stuff we develop doesn't make much sense until there's a bunch of
relevant data. This makes it tricky to develop and demo. Start with the web
test. Have the web test create a bunch of dummy data around today and pull up
the relevant page. This is quite a lot of work and doesn't feel like it
accomplishes much. But now it's dead simple to pick back up where you left off.
You can completely wipe your local database and then ./manage.py clean_test and
boom, you're dropped in the middle of a cleaning.

It also, obviously, gets you started writing the web test. The real value of a
web test is simply that it makes it pretty easy to answer the question, "Is
this thing working, like, as a whole?" And THAT makes it that much easier to
keep things stable.

Stability is like sleep. When you don't have it, life isn't worth living.

Unit tests are the easiest to write, so put your code in unit testable places
as much as possible. That means views and templates are as thin as possible.
If a break should have been caught by a unit test, first write the test, then
fix the break. At the very least you should run your code with a unit
test, even if you don't assert anything.

I used to group all kinds of unit tests into a single TestCase object with no
setUp. The downside here is if one test breaks and you want to

    import pdb
    pdb.set_trace() # DO NOT SUBMIT

deep in your code, even if you just run that TestCase object all the other unit
tests are liable to step into your debugger. So now I think the only good
reason to group unit tests in a TestCase is because they share a setUp.

## URLs

Don't hardcode URLs into templates. You'll notice I hardcoded a lot of URLs
directly into templates. That was a mistake and it's bitten me many times. Use
django's reverse function to calculate urls and pass those urls to the template
via the context.

## My promise to my team

I am a firm believer in victory without bloodshed. Bad vibes are a big red flag
to me. A house divided against itself can't stand. We need teamwork, and good
vibes are essential to teamwork.

My opinion isn't shared by everybody in this company. But there are a small
group of us who can do what we want. I got there strategically. I basically
showed up and started writing software.  After 6 months, a) the company was
utterly dependent on my software, and b) they started paying me. The first
source of my power is simply being very useful. My second source of power is
having the wisdom to reject bullshit early in the process.

My promise is, as long as we're useful and our vibes are good, I believe I can
shield us from bullshit. I believe I can block bullshit from ever getting a
foot in the door. At this point in my career, that's my dream. A job I enjoy
doing things that matter with a minimum of bullshit.

## Culture

I think if you really want engineers to do a good job, they have to actually
love the work. If you ask me, traditional carrot and stick approaches make the
assumption that engineers don't love their jobs and can't be trusted to work
unless you force them on some level. So I really don't like those. I feel like,
if that's how you're managing, that means you've already admitted you lost the
single most important factor: intrinsic motivation.

My idea is to create an environment that reduces toxic extrinsic motivations
which cause burnout and self centered behavior. There's not a lot of personal
glory out there. We live and die as a team. So there's no sense being
territorial because that just makes it hard to go on vacation. There's no sense
grinding on a project you dislike because that's not going to get you a raise
or a promotion or anything.

I am trying my hardest to design this team from the ground up with vibes that
say, "We do this job because we WANT to, not because we have to."

If I can get personal for a moment about what motivates me, this code feels
like maybe my best work of art. It really is a remarkable artifact. The most
important thing about it is, it's useful! But it's also beautiful in a way, or
at least I try to make it that way. So every day I get to come in and make art,
think about interesting problems, and chill with a team I love. I want to hang
on to that vibe. I finally love my job.

Intrinsic motivation is, like, loyalty, curiosity, enjoyment, and love. Love
for the team, love for the mission, and love for the work.

You are not allowed to work on projects you don't enjoy.
You are not allowed to work with people you don't enjoy working with.
You are not allowed to come into work until you are ready to work.
You don't have to like everybody.
You don't have to like everything.
It's ok to freak out every now and then.

Forcing yourself to do work you don't really want to causes burnout. Enjoyment
is a sustainability strategy.

Not allowing people to work on projects they don't like has something to do
with why I picked Python instead of Java.

If you can't find interesting work, and you can't keep teammates, then
dude. You're isolated, and you probably hate your job. It's time to ask bigger
questions.

If we can't find anybody who wants to work on a project, then that's a sign
that something is wrong and we need to take a step back, re-evaluate a few key
situations, call in the big guns. I mean, finding good projects for the team is
such an art form. These sorts of problems are best solved months ago.

There aren't a lot of hard and fast rules around here, just guidelines trying
to be wise. There aren't a lot of measurements being taken. So remember the
basics.

Find work you love. Be helpful.

You are highly encouraged to sustain a fulfilling life outside work. That's an
important factor in your buy-in at work.

I am always happy to talk with anybody with a sincere request for information
or features. If a project is a good fit, I am always open to new opportunities
to help. Those are good interruptions. That's constructive.

What isn't constructive is being interrupted by code that keeps freaking out.
We can't get anything new done if we're pinned down by old busted code. That's
why stability is so important. No bug is allowed to sit.

Let's avoid the blame game because that encourages people to hide their
mistakes, and hidden mistakes are hard to deal with. When things go wrong, it's
cool, speak up. We'll assess the situation with humility and humor, and figure
out what changes we can make to avoid it next time.

Don't deploy past 3pm unless you want to work past 8pm. Don't deploy on Friday
unless you want to work on Saturday.

I don't want people under pressure because then they get tunnel vision and make
bad long term decisions. It seems to me that most time pressure is artificial
and unnecessary. Most time pressure ought to have been solved months ago with
better planning and more realistic expectations. Never agree to a dreadline
that's months away. Avoid promises. The whole point is to build something new,
so naturally we can't know how long it will take to make it happen. Things come
up. Requirements change. Priorities change. Go ahead and give estimates, but
never for a project that will take more than a few weeks. We're going to do the
only thing any human ever can do, and that's take steps towards goals.

If code is confusing, then it needs work. Confusing code is hard to modify,
easy to break, and very stressful in a panic situation. As you go about your
projects, notice when you become confused, and take the time to fix it. Take
the time to stabilize. You shouldn't be under a lot of time pressure so there's
no reason to leave important problems unsolved. This is a good long term
strategy.

Avoid big hairy changes. Break it down into steps. One approach is,

git checkout -b my_new_feature  # Create a new branch

As you program, you realize you're about to make a change that could go out on
its own now.

git commit -a -m 'whatever. doesnt matter'
git checkout master

Now make your nice little change

git commit -a -m 'A helpful description of the little change'
git checkout my_new_feature
git merge master -m 'merging in master'

Avoid promising uptime to people. Do your best to engineer in such a way that
things can break for a few hours and it's not the end of the world.

I'm wary of extensive logs. They tend to take on a life of their own, requiring
substantial effort to manage, let alone stay useful. Ideally, you throw an
exception when bad data tries to get into the database in the first place.
That's deterministic and typically easier to fix. It's much harder to
retroactively find out where bad data came from by digging through logs. But
also, the system is complicated enough as it is, if you're clever you can
figure out what the heck happened without logs, like, 98% of the time.

For instance, when creating new models, put some thought into unique
constraints. Get them in as early as possible. Then, you're forced to fix
duplicates as you go. It's much harder to add a unique constraint to existing
data because you're pretty much guaranteed to have to fix a bunch of duplicates
first, not to mention dealing with whatever wacky problem brought the weird
data to your attention in the first place.

Garbage in garbage out. Block the garbage as early as possible with hard
errors.

Know your assumptions and check for them. Raise an exception or use
errors/models.py as soon as anything fishy happens. Pay attention to the emails
and fix them. Don't allow an email to continue sending. Do this relentlessly
until your system handles every last wacky corner case its ever encountered and
stops emailing you. Sometimes handling a corner case seems to take much more
effort than it deserves, but that's ok. The real point of all that effort is a
system that's so stable you can ignore it entirely and focus completely on a
new project.

No heroics. We're not here to dig a ditch, where working a 12 hour day might be
helpful on some level. What we're doing is more like puzzle solving. Insight
counts more than effort. Every line of code we write is a line of code we have
to maintain, and honestly, people don't really enjoy maintaining code,
especially when the engineer had something to prove. More than people realize,
the right move is, do nothing.

I'm not gonna grade you on a scale from 0 to rockstar. Rockstars are bad at
teamwork. Rockstars are bad at service. We're not here to be impressive, we're
here to enjoy ourselves and be useful. There's a huge difference between
impressive and useful. Craft good code that accomplishes goals. That's
sustainable. And sustainability leads to longevity, and if you ask me,
longevity is obviously a really important factor in productivity. I mean, code
gets real big. Of course you need to be around for a while, developing that
love of the code, the team, and the mission, if you really want to get anything
done.

What are we optimizing for here exactly? An idea I have is, let's optimize for
the percentage of problems solved. New problems urge us to write new code. But
that's only half the picture. An important dynamic here is not introducing new
problems! Tech entropy is the tendency for all code to break over time, so
every line of code we write tends to introduce problems. That's the dynamic
that urges us to minimize code.

In terms of monetary compensation, I just want everyone to feel like they have
more than enough to live a good life, and that they're being treated fairly. If
we can accomplish that, then for the vast majority of the time we can put
distractions to the side and get some work done.

## Prioritization meetings

I have barely any patience at all for scheduled meetings in conference rooms.
The same goes for most forms of corporate homework. I don't handle impromptu
harangings about schedules and priorities very well, and I am not a fan of
formal performance evaluations.

But there is a need for SOME kind of meeting where leadership can hear what's
up and pick priorities. Here's how we approach it.

Anybody comes up with bite sized project ideas. Folks are, of course,
encouraged to have big dreams and long term vision, but I don't schedule and
prioritize on a 6 month level because things change too fast. Rather, once a
month or so, everybody with project ideas joins us, pitches their project, and
then we decide what we'll focus on for the next month or so.

Your project is likely to get prioritized if it
a) Is small.
b) Makes logical sense. Don't overthink this one. I just mean, does everybody
understand what your words literally mean. When you talk, do I become confused.
c) Is immediately useful.
d) Helps us work towards our core goal of capitalizing rooms in buildings
through any number of strategies such as short term rentals, long term /
corporate rentals, F&B, and leases.

Your project is likely to get sent back to the drawing board if it's too vague,
or if it's missing important pieces of the puzzle. Then it's your
responsibility to de-mystify the situation.

The best project pitches are just a paragraph. If you can't describe it in a
few sentences, how am I supposed to spend a few weeks building it?

The beauty of this approach is that it's so reasonable. It sounds so easy! But
you'd be surprised how well it cuts down on project noise. For starters, I'm
not being dragged into 2 hour long brainstorming meetings by folks who don't
really know what they want.

## Code style

It's hard to engage with dry, confusing, frustrating, verbose, and humorless
code. My goal is code that's actually enjoyable. That's my best idea for
encouraging people not to abandon existing code, which is a strategy for
causing less new code, which is ultimately a stability and productivity
strategy.

Above all, fix confusion. Get the abstractions right. But also, feel free to
give it a sense of humor. Make it conversational. Make it readable.

No swearing or dirty jokes though. I have daydreams of pair "programming" with
non programmers. I love answering people's questions by pulling up the code and
walking them through it. Expect eyes on your code.

I had a hard time deciding between this_for_python, thisForJavascript, this-for-html

vs

this_for_python, this_for_javascript, this_for_html

I went with all underscores all the time. I guess the important thing is that
we have a standard at all and stick to it, which honestly I do a B- job of.
Classic.

## Where do I put this Javascript?

Javascript is a bit of a mess. It has some serious weaknesses that are hard to
articulate. It's not like Python where you can import particular things from
particular files. The default thing is to include a pile of files that all go
in the, like, global scope, are imported in no particular order, and don't
themselves describe what files they depend on. So you end up with these 10,000
line long Javascript files that are basically an unruly list of the business
logic required by the pages. Page A code is right next to Page W code, and they
have nothing to do with each other.

There are frameworks that try to make sense of this situation, development time
transpilers and such, but I don't know. It all seems a bit over engineered to
me. For starters, transpilers make debugging a pain. If somebody has the
obfuscater turned on, forget about it. JQuery is definitely a win in terms of
low complexity and high power. Angular is hair-pulling-out complex and only
sightly higher power. I guess if we were making very impressive websites full
of animations and smooth transitions between layouts, a highly complicated
framework might be worth it.

But we're making choring software. We make tables and forms for simple,
effective communication.

In terms of frameworks and libraries and such, my hope is to keep it simple. We
have JQuery and Handlebars. That's, like, shorthand plus templates. Example: we
COULD get a fancy date picker, but these days you can just use
<input type="date"> and that's good enough.

Widely useful utility functions are in static/js/util.js and just go in the
global scope. Easy.

Business logic gets encapsulated thoughtfully, often in objects. A common thing
is, like, there's a Ticket Javascript class that uses the ticket Handlebars
template to render itself. Both the class and the template are embedded
directly in the my_tickets.html (or whatever) django template. That way, you
can find them.

Django templates can inherit. So if you've got business Javascript that makes
sense on 3 closely related pages, embed that Javascript directly in a single
base template.

I'm not really married to any of this. I just want to be able to find, read,
and modify client side code.

## Nontrivial model changes in Django

Django can't move a model from one app to another.

Django can't rename a base class, or change the base class of a model. Well,
it's complicated. Django doesn't care what you do with Abstract base classes as
long as the fields don't change. But if we're talking about there being an
additional table now, forget it.

Django can rename a class (even then, not always, and in precisely the most
annoying way, keep reading), but that's about as fancy a task as it can manage
when it comes to moving classes around.

So I think the answer here is usually just to do it the hard way. You got
system 1 going. You want to make it look like system 2. Well, keep system 1
going, program up system 2 as well, and only when system 2 is totally up and
running in parallel with system 1, then you can "remove" system 1.

For instance. Let's say you've got my_app.MyClass already in production with
data and active use. But then you realize, you want to create
other_app.BaseClass and you want my_app.MyClass to inherit from it. First,
create class my_app.MyClass2(other_app.BaseClass). Do the arduous work of
making MyClass and MyClass2 have baaaasically the same functions and fields.
You'll probably have to change both and have them meet somewhere in the middle.
Next you do something, like, update MyClass with a OneToOne field that points
towards MyClass2, and give MyClass a function which creates or updates its
MyClass2 to match. Probably put that function in MyClass.save. Deploy that.
Now, in production, call this function on every existing MyClass so your data
is not only duplicated in MyClass2, it's kept up to date. You now have a
perfect duplicate situation. Note that everything else is still using MyClass
by the way. But now it's time to change that. Your next change switches
everything over to MyClass2.

The next change deletes MyClass. Then, rename MyClass2 to MyClass. Then, this
part gets really disconcerting. When you try to run these latest migrations,
at least the last time I did this, they failed once! Something about a field
from the original MyClass not being in the new version of MyClass? But anyway I
just reran the migrations and this time they worked.

## Retiring an entire Django app

For instance I retired stayd/listings

The trick is that migrations from other apps might reference your app which
prevents you from removing the entire folder. I started with the directions on
https://simpleisbetterthancomplex.com/tutorial/2016/07/26/how-to-reset-migrations.html
but you should be able to just use these following directions.

0. Update your code so that nothing at all references the app you want to
delete. You can't yet remove the app from settings.py though. I'm not certain
if you can delete all the app's tables themselves... you might get inscrutable
error messages. Maybe work on a new branch and try it out. Then come back and
update these docs.

The point is, get the database to the state you want it to be at for this
whole process. Migrating in the middle of this process gets real ugly so
get all your changes in now.
1. python manage.py makemigrations, commit, deploy, python manage.py migrate
on all databases. Make sure everything is up to date everywhere and that tests
are passing.
2. This command helps you keep track of the migration situation. You'll run it
often.

    python manage.py showmigrations

3. Locally,

    python manage.py migrate --fake my_app zero

That will undo the migrations in my_app, but ALSO the migrations that depend
on those migrations! So do showmigrations to make sure you understand what's
up. If it removed any migrations from other apps, zero those apps out too.
python manage.py migrate --fake my_dependent_app zero

4. Locally, remove the files for the migrations that got "undone".

    git rm my_app/migrations/0*.py
    git rm my_dependent_app/migrations/0*.py

5. Now it's time to totally remove that app you don't want from settings.py and
   also

    git rm -r my_app
    rm -rf my_app

5. python manage.py makemigrations
6. Locally, pretend you installed those new initial migrations you made.

    python manage.py migrate --fake-initial

7. Run the tests.
8. DO NOT GIT COMMIT AND DEPLOY YET!
8. On all other databases such as stage and production,

    heroku run bash -a stayd-stage
    ./manage.py migrate --fake my_app zero
    ./manage.py migrate --fake my_dependent_app zero

8. Remove this line from Procfile

    release: python manage.py migrate

9. NOW git commit and deploy.

9. Then fake the migrations in stage and prod

python manage.py migrate --fake-initial

BUG ALERT

Today when I tried to run that in stage I got

TypeError: sequence index must be integer, not 'slice'

at

python3.6/site-packages/django/db/backends/postgresql/introspection.py", line 69, in <listcomp>

So I basically just manually copied the entries in django_migrations from my
local database to stage and prod instead.

END BUG ALERT

10. Finally, revert Procfile so it once again has the line

    release: python manage.py migrate

## SQL Migrations

Ideally, you just ./manage.py makemigrations all the time. So, do one migration
where you simply rename the field, so Django is smart enough to ask if you're
just renaming the field, then do a second migration to change the help_text or
whatever. Do stupid tricks like that to avoid manual migrations.

Even if you want to modify data as part of the migration,
you probably don't want to do that as part of the migration file. That
gets weird because it's unclear which version of the models we're talking about
here within migration files (before or after?) and in my experience Django gets
just as confused and loves to throw up incomprehensible errors.

Also, from time to time we squash the migrations because once you've got 100
migrations on an app it starts to slow the tests. So just know that your manual
migration is going to get chucked, so if it's a vital step that wouldn't be
captured from totally reset migrations, that's a problem.

So my recommendation is to makemigrations, then create a ./manage.py command or
whatever, maybe even just open up a shell to stage and prod, and do your data
manipulation that way. Now you can do a second round of makemigrations.

A common problem is, you're developing multiple features on multiple branches,
and the migrations clash. Here's a sure fire way to get back to sanity locally
by destroying your local database. Obviously never ever do that on stage or
production. If we let clashing migrations make it all the way to stage, oh boy.

If you see trouble coming but your database is still ok, you can always make a
backup before you tackle the hard stuff.

$ sudo su - postgres
$ psql
$ CREATE DATABASE stayddev_2;
$ GRANT ALL ON DATABASE stayddev_2 TO stayduser;
$ \q
$ pg_dump stayddev | psql stayddev_2

Here's how you wipe out and reinstall an empty database, which by the way is
basically what happens under the hood every time you run tests.

$ sudo su - postgres
$ psql
$ \connect stayddev
$ DROP SCHEMA public CASCADE;
$ CREATE SCHEMA public;
$ GRANT ALL ON SCHEMA public TO postgres;
$ GRANT ALL ON SCHEMA public TO public;
$ \q
$ exit
$ ./manage.py migrate
$ ./manage.py createsuperuser

## What's up with all the duplicated Apply stuff?

Man, 20% of your projects cause 80% of the cruft. This was for an Owner's
Dashboard that went into immediate disuse. It was conceived of to be impressive
and to solve a need we didn't have yet, and probably never will have.

There's basically 2 copies of Apply. The first gets modified as we go to make
our actual owner's dashboard. The other we pretty much leave alone for
reference.
You can see its own overview at
http://127.0.0.1:8000/scrap_heap/apply/index.html
Or check out the original dashboard we worked off of at
http://127.0.0.1:8000/scrap_heap/apply/dashboard.8.html

I used a css precompiler for this stuff.

sudo npm install -g sass
sass --watch dashboard/dashboard.scss static/css/dashboard.css

## Vim

Here's how I show what class and function I'm in.

sudo apt-get install ctags
cd ~/stayd
ctags -R .  # You have to run this to regenerate tags

This is Vundle stuff, a package manager for vim

git clone https://github.com/VundleVim/Vundle.vim.git ~/.vim/bundle/Vundle.vim

Put this at the top of your ~/.vimrc

" vundle stuff
filetype off
set rtp+=~/.vim/bundle/Vundle.vim
call vundle#begin()
Plugin 'VundleVim/Vundle.vim'
Plugin 'bling/vim-airline'
Plugin 'majutsushi/tagbar'
call vundle#end()
let g:airline#extensions#tagbar#flags = 'f'  " show full tag hierarchy
let g:airline_section_a = ''
let g:airline_section_y = ''
let g:airline_section_z = ''

Then 

vim ~/.vimrc
:source %
:PluginInstall

The default Javascript highlighting in Vim is pretty bad. I followed the
directions on https://www.vim.org/scripts/script.php?script_id=1491 to install
a better js syntax highlighter.

I also added this to my ~/.vimrc which makes javascript in html files use the
whole file as context.

autocmd BufEnter *.html :syntax sync fromstart

## Setting up from scratch on Heroku, hypothetically

Let's say you wanted to tear EVERYTHING down and start all over again,
not just in your local environent, but everywhere.

DO NOT RUN THESE COMMANDS EVER! This is purely educational.

heroku pipelines:destroy stayd-web
heroku apps:destroy stayd-stage
heroku apps:destroy stayd-prod

heroku apps:create stayd-stage --remote stayd-stage --org stayd-developers
heroku apps:create stayd-prod --remote stayd-prod --org stayd-developers

git push stayd-stage master
heroku run python manage.py migrate --app stayd-stage
heroku run python manage.py createsuperuser --app stayd-stage
heroku open --app stayd-stage

git push stayd-prod master
heroku run python manage.py migrate --app stayd-prod

Now go to Heroku and set up the Pipeline.
- Create the pipeline. Name it stayd-web.
- Go to the pipeline settings and set the owner to stayd-developers
- Add the apps to the pipeline.
- In the pipeline settings turn on CI.
- In the stayd-stage deploy settings turn on auto deploy and check
  'Wait for CI to pass before deploy'

Now set up background threads. Here's how to do it on stage.
heroku addons:create redistogo:nano -a stayd-stage

There are many more comments on background threads and the redis queue and such
in util/background.py and in worker.py
