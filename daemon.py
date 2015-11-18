#!/usr/bin/env python

import sys
import os
import time
import atexit
from signal import SIGTERM
from datetime import datetime
import logging
import subprocess
import smtplib
import traceback
import src
import glob

class BashError(Exception):
    pass

class Daemon(object):
    def __init__(self, pidfile, stdin='/dev/null', stdout='/dev/null', stderr='/dev/null'):
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr
        self.pidfile = pidfile

    def daemonize(self):

        try:
            pid = os.fork()
            if pid > 0:
                sys.exit(0)
        except OSError, e:
            logging.fatal("fork #1 failed: %d (%s)\n" % (e.errno, e.strerror))
            sys.exit(1)

        os.chdir("/")
        os.setsid()
        os.umask(0)

        try:
            pid = os.fork()
            if pid > 0:
                sys.exit(0)
        except OSError, e:
            logging.fatal("fork #2 failed: %d (%s)\n" % (e.errno, e.strerror))
            sys.exit(1)

        sys.stdout.flush()
        sys.stderr.flush()
        si = file(self.stdin, 'r')
        so = file(self.stdout, 'a+')
        se = file(self.stderr, 'a+', 0)
        os.dup2(si.fileno(), sys.stdin.fileno())
        os.dup2(so.fileno(), sys.stdout.fileno())
        os.dup2(se.fileno(), sys.stderr.fileno())

        atexit.register(self.delpid)
        pid = str(os.getpid())
        file(self.pidfile, 'w+').write("%s\n" % pid)

    def delpid(self):
        os.remove(self.pidfile)

    def start(self):

        try:
            pf = file(self.pidfile, 'r')
            pid = int(pf.read().strip())
            pf.close()
        except IOError:
            pid = None

        if pid:
            logging.fatal("pidfile {} already exist. Daemon already running?".format(self.pidfile))
            sys.exit(1)

        self.daemonize()
        self.run()

    def stop(self):

        try:
            pf = file(self.pidfile, 'r')
            pid = int(pf.read().strip())
            pf.close()
        except IOError:
            pid = None

        if not pid:
            logging.fatal("pidfile {} does not exist. Daemon not running?".format(self.pidfile))
            return

        try:
            while 1:
                os.kill(pid, SIGTERM)
                time.sleep(0.1)
        except OSError, err:
            err = str(err)
            if err.find("No such process") > 0:
                if os.path.exists(self.pidfile):
                    os.remove(self.pidfile)
            else:
                print str(err)
                sys.exit(1)

    def restart(self):

        self.stop()
        self.start()

    def run(self):
        pass


class Teacher(Daemon):
    def start(self, config):
        self.config = config
        self.consume_config()
        self.last_action = datetime.now()
        super(Teacher, self).start()

    def consume_config(self):
        self.min_interval = self.config.getint('main', 'min_interval')
        self.sleep = self.config.getint('main', 'sleep_time')
        self.params = self.config.get("params", "params")
        self.input_file = self.config.get("main", "input_file")
        self.out_file = self.config.get("main", "out_file")
        self.cache_file = self.config.get("main", "cache_file")
        self.euser = self.config.get("email", "user")
        self.epass = self.config.get("email", "pass")
        self.subject = self.config.get("email", "sub")
        self.recipents = self.config.get("email", "recipents")

    def run(self):
        while 1:
            time.sleep(self.sleep)
            if (datetime.now() - self.last_action).seconds > self.min_interval:
                try:
                    logging.info("Starting up " + str(self.last_action))
                    self.last_action = datetime.now()
                    self.teachvw()
                except Exception as e:
                    self.send_email(traceback.format_exc())

    def restart(self, config):
        self.stop()
        self.start(config)

    def teachvw(self):
        self._prepare_input()
        command = "vw {data_file} -f {output} {params}  --cache_file {cache_file}"
        command = 'echo "{}"'.format(command.format(data_file=self.input_file,
                                                    output=self.out_file,
                                                    cache_file=self.cache_file,
                                                    params=self.params))
        process = subprocess.Popen(command.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        a, b = process.communicate()
        if process.returncode != 0:
            logging.fatal(b.strip())
            raise(BashError)
        logging.info(a.strip())
        self._remove_input()

    def _prepare_input(self):
        files = self.get_files()
        # raise
        command = 'cp /home/gbaranowski/test_in {input_file}'.format(input_file=self.input_file)
        process = subprocess.Popen(command.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        a, b = process.communicate()
        if process.returncode != 0:
            logging.fatal(b.strip())
            raise(BashError)
        logging.info(a.strip())

    def _remove_input(self):
        os.remove(self.input_file)

    def send_email(self, body):
        recipient = self.recipents.split(",")
        FROM = self.euser
        TO = recipient if type(recipient) is list else [recipient]
        SUBJECT = self.subject
        TEXT = body
        # Prepare actual message
        message = """\From: %s\nTo: %s\nSubject: %s\n\n%s
        """ % (FROM, ", ".join(TO), SUBJECT, TEXT)
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.ehlo()
        server.starttls()
        server.login(self.euser, self.epass)
        server.sendmail(FROM, TO, message)
        server.close()

    def get_files(self):
        now = datetime.now()
        return glob.glob("/home/model/y/modelTester.log.*.gz")



