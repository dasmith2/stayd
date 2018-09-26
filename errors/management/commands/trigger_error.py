from commands.stayd_command import StaydCommand


class Command(StaydCommand):
  def run(self, verbose):
    a = 1 / 0
    print(a)

  def name(self):
    return 'trigger_error'
