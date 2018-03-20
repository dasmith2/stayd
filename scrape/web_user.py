class WebUserManager(object):
  def get_web_users(self):
    return [
        WebUser(
            'Abe', '198.12.72.230', 21283, 'MariaHardyKanishf544@gmail.com',
            'ExecRes2017!!!!', 'execrEs7102'),
        WebUser(
            'Alex Grinzel', '198.12.72.206', 21316,
            'AngelitaSMorrison@gmail.com', 'test1234', 's9!!gttoG38UJhd4'),
        WebUser(
            'Aubrey Glass', '198.12.72.230', 21235, 'AutumnTGlass@gmail.com',
            'ExecRes2017', 'b9q$ntPsxIOSKjp#'),
        WebUser(
            'Augusta', '198.23.168.220', 21288, 'AugustaAAustin@gmail.com',
            'test1234', '3W+H>ujY}CVZjt<G')]

  def get_web_user(self, name):
    for web_user in self.get_web_users():
      if name == web_user.name:
        return web_user


class WebUser(object):
  def __init__(
      self, name=None, ip=None, port=None, air_uname=None, air_pwd=None,
      gmail_pwd=None):
    self.name = name
    self.ip = ip
    self.port = port
    self.air_uname = air_uname
    self.email = air_uname
    self.air_pwd = air_pwd
    self.gmail_pwd = gmail_pwd
