#!/usr/bin/env python

import sys, time
from daemon import Teacher
import ConfigParser
from os import path
import logging, traceback


def get_config():
    base_dir = path.dirname(path.realpath(__file__))
    config = ConfigParser.RawConfigParser()
    config.read(path.join(base_dir, 'config.ini'))
    return config





if __name__ == "__main__":
    daemon = Teacher('/tmp/vwteacher.pid')
    try:
        if len(sys.argv) == 2:
            if 'start' == sys.argv[1]:
                daemon.start(get_config())
            elif 'stop' == sys.argv[1]:
                daemon.stop()
            elif 'restart' == sys.argv[1]:
                daemon.restart(get_config())
            else:
                print "Unknown command"
                sys.exit(2)
            sys.exit(0)
        else:
            print "usage: %s start|stop|restart" % sys.argv[0]
            sys.exit(2)
    except Exception as e:
        logging.error(traceback.format_exc())
        raise

