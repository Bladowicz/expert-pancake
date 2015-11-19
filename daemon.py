#!/usr/bin/env python

import sys
import os
import time
import atexit
from signal import SIGTERM
import datetime
import logging
import subprocess
import smtplib
import traceback
import src
import glob


def teachvw_errors(fn):
    def wrapper(*args, **kargs):
        try:
            return fn(*args, **kargs)
        except BashError as e:
            logging.fatal(e.explain())
            args[0].send_email(e.explain())
        except:
            args[0].send_email(traceback.format_exc())
    wrapper.__name__ = fn.__name__
    return wrapper

class BashError(Exception):

    def __init__(self, command, err_msg):
        self.command = command
        self.err_msg = err_msg

    def explain(self):
        return "BASH : {}\nERROR : {}".format(self.command, self.err_msg)

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
        logging.info("XXX STARTING XXX")
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
        logging.info("XXX STOPING XXX")
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
        logging.info("XXX RESTARTING XXX")
        self.stop()
        self.start()

    def run(self):
        pass


class Teacher(Daemon):
    def start(self, config):
        self.config = config
        self.consume_config()
        self.last_action = datetime.datetime(1, 1, 1, 0, 0)
        super(Teacher, self).start()

    def consume_config(self):
        self.min_interval = self.config.getint('main', 'min_interval')
        self.sleep = self.config.getint('main', 'sleep_time')
        self.params = self.config.get("params", "params")
        self.input_file = os.path.join("/tmp/", self.config.get("main", "input_file"))
        self.out_file = self.config.get("main", "out_file")
        self.cache_file = self.config.get("main", "cache_file")
        self.euser = self.config.get("email", "user")
        self.epass = self.config.get("email", "pass")
        self.subject = self.config.get("email", "sub")
        self.recipents = self.config.get("email", "recipents")
        self.time = self.config.getint("main", "history_length")

    def run(self):
        while 1:

            if (datetime.datetime.now() - self.last_action).seconds > self.min_interval:
                logging.info("########### STARTING UP ############")
                tmp = datetime.datetime.now()
                self.teachvw()

                # try:
                #     self.teachvw()
                # except BashError as e:
                #     logging.fatal(e.explain())
                #     self.send_email(e.explain())
                # except:
                #     self.send_email(traceback.format_exc())
                self.last_action = tmp
            self._wait()

    def _wait(self):
        s = (datetime.datetime.now() - self.last_action).seconds
        if s >= 0:
            s = self.min_interval - s
        else:
            s = self.min_interval
        logging.info("I will now sleep for next {}".format(str(datetime.timedelta(seconds=s))))
        time.sleep(s)

    def restart(self, config):
        self.stop()
        self.start(config)

    @teachvw_errors
    def teachvw(self):
        self._prepare_input()
        command = "vws {data_file} -f {output} {params}  --cache_file {cache_file}".format(data_file=self.input_file,
                                                    output=self.out_file,
                                                    cache_file=self.cache_file,
                                                    params=self.params)
        logging.info("Teaching rabbit how to math with : {}".format(command))
        process = subprocess.Popen(command.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        a, b = process.communicate()
        if process.returncode != 0:
            raise(BashError(command, b.strip()))
        self._check_answer("Rabbit has learned and commented", a)
        self._check_answer("Rabbit has learned and nagged", b)
        # a = a.strip()
        # if a:
        #     logging.info("Rabbit has learned and commented : {}".format(a))
        # b = b.strip()
        # if b:
        #     logging.info("Rabbit has learned and nagged : {}".format(b))
        self._remove_input()

    def _check_answer(self, text, msg):
        msg = msg.strip()
        if msg:
            logging.info("{} : {}".format(text, msg))

    def _prepare_input(self):
        files = self.get_files()
        os.chdir("/home/model/model-class-updater-1.0")
        command = '/bin/bash run.sh 1 {} {}'.format(self.input_file, " ".join(files))
        logging.info("Starting file merging with : {}".format(command))
        process = subprocess.Popen(command.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        a, b = process.communicate()
        if process.returncode != 0:
            raise(BashError(command, b.strip()))
        self._check_answer("Input file prepared with output", a)
        self._check_answer("Input file prepared with problems", b)
        # logging.info("Input file prepared with output : {}".format(a.strip()))

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
        now = datetime.datetime.now()
        then = now - datetime.timedelta(hours=self.time)
        result = []
        for f in glob.glob("/home/model/y/modelData.log.*.gz"):
            d = datetime.datetime.strptime(os.path.basename(f), 'modelData.log.%Y-%m-%d-%H.gz')
            if d > then and d < now:
                result.append(f)
        if len(result) == 0:
            raise(BashError("Files", "No files found."))
        else:
            logging.info("Files found : {}".format(len(result)))
        return result




