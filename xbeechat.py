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

"""
XbeeChat class is an asynchronous queueing system that can handle packet transmission
between Xbee radios. The strcture of packets is based on XBee API mode frame and the
transmission function is based on python-xbee library(https://code.google.com/p/python-xbee/)
"""
class XbeeChat(threading.Thread):
    def __init__(self, port, address, callback = None):
        super(XbeeChat, self).__init__()
        self.setDaemon(True)
        self.port = port
        self.name = "Xbee Chat Worker Thread on port {}".format(self.port)
        self.log = logging.getLogger("xbee[{}]".format(self.port))
        self.address = address

        self.inflight = {}

        self.callback = callback
        self.cmd_queue = Queue.Queue()

        self.ser = serial.Serial(self.port, 9600, rtscts = True)
        self.xbee = XBee(self.ser, callback = self.on_packet)
        self.start()

    """
    The callback function which analysis incoming packet and display the result
    """
    def on_packet(self, pkt):
        tx_status_codes = {'\x00': 'Success', '\x01': 'No ACK', '\x02': 'CCA fail', '\x03': 'Purged'}

        if pkt and 'id' in pkt and pkt['id'] == 'tx_status':
            frame_id = struct.unpack("B", pkt['frame_id'])[0]
            self.log.debug("TX status: frame_id: {}, status: {}".format(frame_id,
                                                                       tx_status_codes[pkt['status']]))

            if frame_id in self.inflight:
                self.inflight[frame_id].status = struct.unpack("B", pkt['status'])[0]
                self.inflight[frame_id].evt.set()

        elif pkt and 'id' in pkt and pkt['id'] == 'rx':
            self.log.debug("RX: src: {}, rssi: -{} dbm, data: {}".format(struct.unpack(">H", pkt['source_addr'])[0],
                                                                   struct.unpack("B", pkt['rssi'])[0],
                                                                   " ".join(["{:02x}".format(ord(i)) for i in pkt['rf_data']])
                                                                   ))
        else:
            self.log.info("RX: {}".format(pkt))

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
        self.log.info("packet of len: {} queued".format(len(payload)))
        return evt
    """
    Configure the Xbee and then keep deqeueing stored packets and then send by calling send
    function in python-xbee
    """
    def run(self):

        self.xbee.send("at", frame_id= 'x', command="VR")
        self.xbee.send("at", frame_id= 'y', command="HV")


        self.xbee.send("at", frame_id= 'z', command="AP", parameter=struct.pack(">H", 1))
        self.xbee.send("at", frame_id ='a', command="MM", parameter="\x02")
        self.xbee.send("at", frame_id= 'z', command="MY", parameter=struct.pack(">H", self.address))
        self.xbee.send("at", frame_id= 'z', command="MY")

        time.sleep(1)

        i = 1
        while True:

            cmd, params, evt = self.cmd_queue.get()

            if cmd == "tx":
                self.log.info("TX: frame_id: {}, dest_addr: {}, data: {}".format(i,
                                                                                 params['dest'],
                                                                                 params['data']))
                self.inflight[i & 0xff] = evt

                self.xbee.send("tx",
                               frame_id = struct.pack("B", i & 0xff),
                               dest_addr = struct.pack(">H", params['dest']),
                               data = params['data'])
            elif cmd == "quit":
                self.log.info("shutting down")
                self.xbee.halt()
                self.ser.close()
                break
            else:
                self.log.error("Invalid command recieved: {}".format(cmd))

            i = i + 1
            # don't send frame id = 0 becuase no tx status is sent back.
            if i & 0xff == 0:
                i = 1

    def close(self):
        self.cmd_queue.put( ('quit', None, None))



