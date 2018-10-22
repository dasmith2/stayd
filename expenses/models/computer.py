"""
Ideally this thing, and only this thing, knows about all the wacky expense
APIs. Those are bento, xxero, and properly at the moment. It does all the
complicated things it needs to do in order to write to
expenses.models.expenses. The rest of the project is welcome to read from
expenses.models.expenses.

That's how we keep the complications of a laundry list of expense APIs from
complicating the rest of the project.
"""
