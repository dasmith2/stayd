from abc import abstractmethod


class ReservationManagerIsDown(Exception):
  pass


class GenericSyncer(object):
  """ At the moment, Guesty details are scattered everywhere.
  This is bad, because we're liable to replace Guesty or even run a
  different reservation management system (RMS) in parallel. So this class
  is meant to provide an interface that Guesty, and future RMSs, will
  implement. """

  @abstractmethod
  def set_id_verified(self, reservation):
    raise NotImplementedError('set_id_verified')

  @abstractmethod
  def set_phone_email(self, reservation, phone, email):
    raise NotImplementedError('set_phone_email')
