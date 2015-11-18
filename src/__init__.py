import os
base_dir = os.path.split(os.path.dirname(os.path.realpath(__file__)))[0]
log_dir = os.path.join(base_dir, 'logs',)
try:
    os.makedirs(log_dir)
except OSError:
    pass

from logger import start_logger
start_logger(os.path.join(log_dir, "base.log"))
