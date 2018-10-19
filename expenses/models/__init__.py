# flake8: noqa:F401
""" Ideally, the only thing that knows about Xero and Bento is
expenses.models.computer Ideally, nothing knows about expenses.models.computer
except the Django framework. expenses.models.computer writes to
expenses.models.expenses, and stats or whatever is welcome to read from
expenses.models.expenses.

So if we ever wanna, say, replace Bento or add some wacky API related to
expenses or change the way we handle Xero, then there's one place to look:
expenses.models.computer. As long as expenses.models.expenses remains
unchanged, the rest of the system can remain totally oblivious.

Hence, avoid importing directly from expenses.models. Here's why. Let's say
stats did from expenses.models import Expense It's not the end of the world,
but since computer stuff is also in expenses.models, now stats kind of depends
on expenses.models.computer which definitely depends on xxero and bento, so now
stats depends on bento, which is way too complicated and a bad idea. """

from expenses.models.expenses import ReservationExpense, Expense
