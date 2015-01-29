'''
The MIT License (MIT)

Copyright (c) <2014> <Alan Marchiori, Jinbo Wang>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in
    all copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
    THE SOFTWARE.

'''

import logging
import threading
import serial
import time
import struct
import Queue
from xbee import XBee
import datetime

class TxStatus:
    Success = 0
    NoACK = 1
    CCAFail = 2
    Purged = 3
    def __init__(self):
        self.evt = threading.Event()
        self.status = None
        self.times ={'create': datetime.datetime.now()}
    def wait(self, timeout = None):
        self.evt.wait(timeout)
        self.times['dequeue'] = datetime.datetime.now()
#       logging.getLogger(__name__).info("Queue delay was: {}".format((self.times['dequeue']-
        return self.status

def hexdump(x):
    if x:
        return " ".join(["{:02x}".format(ord(i)) for i in x])
    else:
        return "None"
"""
XbeeChat class is an asynchronous queueing system that can handle packet transmission
between Xbee radios. The strcture of packets is based on XBee API mode frame and the
transmission function is based on python-xbee library(https://code.google.com/p/python-xbee/)
"""
class XbeeChat(threading.Thread):
    def __init__(self, port, panid, address, channel = 15, callback = None):
        super(XbeeChat, self).__init__()
        self.setDaemon(True)
        self.port = port
        self.name = "Xbee Chat Worker Thread on port {}".format(self.port)
        self.log = logging.getLogger("xbee[{}]".format(self.port))
        self.address = address
        self.panid = panid
        if channel < 11 or channel > 26:
            raise Exception("Invalid channel, must be 11-26 (XBee), other are not supported.")
        self.channel = channel

        self.seqno = 1
        self.inflight = {}

        self.callback = callback
        self.cmd_queue = Queue.Queue()

        self.startedEvt = threading.Event()

        self.ser = serial.Serial(self.port, 38400, rtscts = True)
        self.ser.flushInput()
        self.ser.flushOutput()
        self.xbee = XBee(self.ser, callback = self.on_packet, escaped = True)
        self.start()
        if not self.startedEvt.wait(5):
            raise Exception("XBee send thread failed to start") 
        
        try:
            self.configure([('AP', struct.pack(">H", 2)),
                    ('MM', "\x02"),
                    ('MY', struct.pack(">H", self.address)),
                    ("CH", struct.pack(">B", self.channel)),
                    ("ID", struct.pack(">H", self.panid)),
                    ("D7", "\x01"),
                    ("D6", "\x01"),
                    ("IU", "\x00"),
                    ("P0", "\x01"),
                    ("P1", "\x00"),
                    ("RN", "\x01"), # random delay slot backoff in CSMA-CA
                    ("AI", None)
                    ])       
        except Exception as x:
            # if we fail at this point, we have to shutdown, then raise the exception
            self.log.info("shutting down")
            self.xbee.halt()
            self.ser.close()
            raise x

    """
    The callback function which analysis incoming packet and display the result
    """
    def on_packet(self, pkt):
        tx_status_codes = {'\x00': 'Success', '\x01': 'No ACK', '\x02': 'CCA fail', '\x03': 'Purged'}

        if 'frame_id' in pkt:    
            frame_id = struct.unpack("B", pkt['frame_id'])[0]
        else:
            frame_id = None
            
        if pkt and 'id' in pkt and pkt['id'] == 'at_response':
            status = struct.unpack("B", pkt['status'])[0]
                        
            if status > 0:
                log = self.log.warn
            else:
                log = self.log.debug
                    
            if 'parameter' not in pkt:
                pkt['parameter'] = None
        
            log("AT response, frame_id: {}, command: {}, parameter: {}, status: {}".format(
                                                                                         hexdump(pkt['frame_id']),
                                                                                         pkt['command'],
                                                                                         hexdump(pkt['parameter']), 
                                                                                         status))                    
            if frame_id not in self.inflight:
                self.log.warn("No matching command packet to this frame_id!")
                
        elif pkt and 'id' in pkt and pkt['id'] == 'tx_status':

            self.log.info("TX status: frame_id: {}, status: {}".format(frame_id,
                                                                       tx_status_codes[pkt['status']]))

            if frame_id not in self.inflight:
                self.log.warn("No matching TX packet to this frame_id!")

        elif pkt and 'id' in pkt and pkt['id'] == 'rx':
            self.log.debug("RX: src: {}, rssi: -{} dbm, data: {}".format(struct.unpack(">H", pkt['source_addr'])[0],
                                                                   struct.unpack("B", pkt['rssi'])[0],
                                                                   hexdump(pkt['rf_data'])))
        else:
            self.log.info("RX: {}".format(pkt))
        if frame_id and frame_id in self.inflight:
            self.inflight[frame_id].status = struct.unpack("B", pkt['status'])[0]
            self.inflight[frame_id].evt.set()

        if self.callback:
            self.callback(self, pkt)

    """
    Queueing packets.
    """
    def send(self, dest, payload):
        evt = TxStatus()

        assert len(payload) <= 100, "Max payload is 100 bytes"
        self.cmd_queue.put(("tx",
                            {'data': payload,
                             'dest': dest},
                            evt))
        self.log.debug("packet of len: {} queued".format(len(payload)))
        return evt
    def sendAT(self, command, parameter = None):
        evt = TxStatus()
        if parameter:
            assert len(parameter) <= 100, "Max parameter length is 100 bytes"
        self.cmd_queue.put(("at",
                                {'command': command,
                                 'parameter': parameter},
                                evt))
        if parameter:
            self.log.debug("at command of len: {} queued".format(len(parameter)))
        else:
            self.log.debug("at command queued")
        return evt
    def configure(self, commands):        
        for c in commands:            
            e = self.sendAT(*c)
            e.wait(2)
            if e.status == None or e.status > 0:
                raise Exception("XBee config failed (status={}).".format(e.status)) 
    """
    Configure the Xbee and then keep deqeueing stored packets and then send by calling send
    function in python-xbee
    """
    def run(self):

        self.startedEvt.set()


        while True:

            cmd, params, evt = self.cmd_queue.get()

            if cmd == 'at':
                self.log.info("AT command: frame_id: {:02x}, command: {}, params: {}".format(self.seqno,                                                                                            
                                                                                            params['command'],
                                                                                            hexdump(params['parameter'])))
                self.inflight[self.seqno & 0xff] = evt
                if 'parameter' in params and params['parameter']:
                    self.xbee.send("at",
                                   frame_id = struct.pack("B", self.seqno & 0xff),
                                   command = params['command'],
                                   parameter = params['parameter']
                                   )
                else:
                    self.xbee.send("at",
                                   frame_id = struct.pack("B", self.seqno & 0xff),
                                   command = params['command'])
            elif cmd == "tx":
                self.log.info("TX: frame_id: {:02x}, dest_addr: {}, data: {}".format(self.seqno,
                                                                                 params['dest'],
                                                                                 params['data']))
                self.inflight[self.seqno & 0xff] = evt

                self.xbee.send("tx",
                               frame_id = struct.pack("B", self.seqno & 0xff),
                               dest_addr = struct.pack(">H", params['dest']),
                               data = params['data'])
            elif cmd == "quit":
                self.log.info("shutting down")
                self.xbee.halt()
                self.ser.close()
                break
            else:
                self.log.error("Invalid command received: {}".format(cmd))

            self.seqno += 1
            # don't send frame id = 0 becuase no tx status is sent back.
            if self.seqno & 0xff == 0:
                self.seqno = 1

    def close(self):
        self.cmd_queue.put( ('quit', None, None))



