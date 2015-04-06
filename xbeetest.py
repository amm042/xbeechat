import logging
logging.basicConfig(level=logging.INFO)

from xbeechat import XbeeChat
from xbeeinit import try_configure
import time

def p0(xb, packet):

    print ("p0", packet)


def p1(xb, packet):

    print ("p1", packet)


#try_configure("/dev/ttyUSB0", 38400)

x1 = XbeeChat(port = "/dev/ttyUSB0", 
              panid = 1234,
              address = 444,
              channel = 16,
              callback = p0)


x2 = XbeeChat(port = "/dev/ttyUSB1", 
              panid = 1234,
              address = 555,
              channel = 16,
              callback = p1)

x1.send(x2.address, "Hello from x1")
time.sleep(0.1)
x2.send(x1.address, "Hello from x2")
    
time.sleep(1)

x1.close()
x2.close()