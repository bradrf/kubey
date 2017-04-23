from datetime import datetime
import dateutil.parser
import dateutil.relativedelta
import dateutil.tz


epoch = datetime.fromtimestamp(0, tz=dateutil.tz.tzutc())


def now():
    return datetime.now(dateutil.tz.tzlocal())


def parse(string, default=None):
    if string is None:
        return default
    return dateutil.parser.parse(string)


def delta(t1, t2):
    return dateutil.relativedelta.relativedelta(t1, t2)


def as_local(stamp):
    return stamp.astimezone(dateutil.tz.tzlocal())


def in_words_from_now(stamp, sep='_', precision='{:0.1f}'):
    if stamp is None:
        return 'never'
    nw = now()
    if nw > stamp:
        words = ('ago',)
        rdate = delta(nw, stamp)
    else:
        words = ('from', 'now')
        rdate = delta(stamp, nw)
    if rdate.days > 0 or rdate.weeks > 0 or rdate.months > 0 or rdate.years > 0:
        return stamp.astimezone(dateutil.tz.tzlocal()).isoformat()
    if rdate.hours > 0:
        value = rdate.hours + (rdate.minutes / 60.0)
        label = 'hours'
    elif rdate.minutes > 0:
        value = rdate.minutes + (rdate.seconds / 60.0)
        label = 'min'
    else:
        value = rdate.seconds + (rdate.microseconds / 1000000.0)
        label = 'sec'
    return sep.join((precision.format(value), label) + words)
