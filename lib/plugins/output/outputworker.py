from __future__ import division
import os, sys
import logging
import logging.handlers
from collections import deque
import threading
from Queue import Empty
try:
	import billiard as multiprocessing
except ImportError, e:
	import multiprocessing
import json
from eventgenconfig import Config
import time

class OutputProcessWorker(multiprocessing.Process):
    def __init__(self, num):
        self.worker = OutputRealWorker(num)

        multiprocessing.Process.__init__(self)

    def run(self):
        self.worker.run()

    def stop(self):
    	self.worker.stopping = True

class OutputThreadWorker(threading.Thread):
    def __init__(self, num):
        self.worker = OutputRealWorker(num)

        threading.Thread.__init__(self)

    def run(self):
        self.worker.run()

    def stop(self):
    	self.worker.stopping = True

class OutputRealWorker:
	stopping = False

	def __init__(self, num):
		# Logger already setup by config, just get an instance
		logger = logging.getLogger('eventgen')
		globals()['logger'] = logger

		globals()['c'] = Config()

		if c.queueing == 'zeromq':
			context = zmq.Context()
			self.receiver = context.socket(zmq.PULL)
			self.receiver.connect('tcp://localhost:5558')

		logger.debug("Starting OutputWorker %d" % num)

		self.num = num

	def run(self):
		if c.profiler:
		    import cProfile
		    globals()['threadrun'] = self.real_run
		    cProfile.runctx("threadrun()", globals(), locals(), "eventgen_outputworker_%s" % self.num)
		else:
		    self.real_run()

	def real_run(self):
		while not self.stopping:
			try:
				if c.queueing == 'python':
					# Grab a queue to be written for plugin name, get an instance of the plugin, and call the flush method
					name, queue = c.outputQueue.get(block=True, timeout=1.0)
					# name, queue = c.outputQueue.get(False, 0)
				elif c.queueing == 'zeromq':
					name, queue = self.receiver.recv_json()
				c.outputQueueSize.decrement()
				tmp = [len(s['_raw']) for s in queue]
				c.eventsSent.add(len(tmp))
				c.bytesSent.add(sum(tmp))
				tmp = None
				plugin = c.getPlugin(name)
				plugin.flush(queue)
			except Empty:
				# If the queue is empty, do nothing and start over at the top.  Mainly here to catch interrupts.
				# time.sleep(0.1)
				pass

def load():
	if globals()['threadmodel'] == 'thread':
	    return OutputThreadWorker
	else:
	    return OutputProcessWorker