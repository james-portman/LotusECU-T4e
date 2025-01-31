import sys, can, argparse
from lib.crc import CRC8Normal
from lib.crp08 import CRP08, CRP08_exception
from lib.fileprogress import Progress

# Some constants
BO_BE = 'big'

class CRP08_uploader:
	errors = {
		0x81: "Not a 7,1 or 8,0 or 9,0 message received",
		0x82: "Error count > 3 (too many Errors)",
		0x83: "Stage3: r13-0x7FED Bit 2 is not set",
		0x85: "Error during flash programming (Hardware related, verify failed - multiple causes)",
		0x87: "Message 9,1 related ?",
		0x88: "Error during flash erase",
		0x89: "Databyte0 of expected First/Next/Subsequent Frame message was not 0x6",
		0x8A: "Programmed Bootloader Version is 0x0 and destination flash address was not 0xA00. Decrypted header Min/Max Bootloader versions are not matching or are zero",
		0x8B: "Decrypted header 'T4E'+0x1F<0x20> is not matching !",
		0x8C: "Header A00_val1(+0x34) > flashed 0xA00 value OR Header A00_val2(+0x38) < flashed 0xA00 value",
		0x8D: "Invalid destination address and/or size",
		0x8E: "Timeout while waiting for data.",
		0x8F: "Test for emptiness of the flash destination address failed. This is valid for 0xA00, 0xA2C, 0xA4C, 0x7C0 (SPI) addresses",
		0x90: "HC908: Error unlocking HC908 with 8 byte passphrase",
		0x96: "More than 0x400 byte received in frame",
		0x97: "First/Next/Subsequent Frame message (0x6) had invalid len (<6 bytes) and/or the CRC was invalid",
		0x98: "Databyte1/2 of expected First/Next/Subsequent Frame message (0x6) did not match the expected frame count value",
		0x99: "Databyte 3/4 of the expected First/Next/Subsequent Frame message (0x6) did not match (total number of frame bytes received)-6 or unknown"
	}

	def __init__(self, interface, channel, p):
		self.interface = interface
		self.channel = channel
		self.p = p
		self.bus = None
		self.crc = CRC8Normal(0x31, initvalue=0x00)
		self.frame_size = 512

	def open_can(self, chunk_can):
		if(self.bus != None): self.close_can()
		self.p.log("Open CAN "+self.interface+" "+self.channel+" @ "+str(chunk_can.can_bitrate)+" kbit/s")
		self.bus = can.Bus(
			interface = self.interface,
			channel = self.channel,
			can_filters = [{
				"extended": False,
				"can_id": chunk_can.can_local_id2,
				"can_mask": 0x7FF
			}],
			bitrate = chunk_can.can_bitrate*1000
		)
		# Workaround for socketcan interface.
		# The kernel filtering does not filter out the error messages.
		# So force library filtering.
		self.bus._is_filtered = False

	def close_can(self):
		if(self.bus == None): return
		self.p.log("Close CAN")
		self.bus.shutdown()
		self.bus = None

	def send(self, cmd, data):
		data = cmd.to_bytes(1, BO_BE) + data
		self.crc.reset()
		self.crc.update(data)
		data += self.crc.get().to_bytes(1, BO_BE)
		offset = 0
		size = len(data)
		while(size > 0):
			chunk_size = min(8, size)
			chunk = data[offset:offset+chunk_size]
			msg = can.Message(
				is_extended_id = False, arbitration_id = 0x51,
				data = chunk
			)
			self.bus.send(msg)
			offset += chunk_size
			size -= chunk_size

	def send_frame(self, data, frame_id):
		offset = frame_id * self.frame_size
		frame = data[offset:offset+self.frame_size]
		header = frame_id.to_bytes(2, BO_BE) + len(frame).to_bytes(2, BO_BE)
		self.send(6, header + frame)

	def send_start(self):
		self.send(7, b"\x01\x00\x00\x00\x00\x00")

	def recv(self, timeout, ui_cb):
		for _ in range(0, int(timeout/0.5)):
			ui_cb()
			msg = self.bus.recv(timeout=0.5)
			if(msg != None): break
		if(msg == None): raise CRP08_exception("No answer!")
		self.crc.reset()
		self.crc.update(msg.data[0:-1])
		if(self.crc.get() != msg.data[-1]):
			raise CRP08_exception("Wrong CRC!")
		return (msg.data[0], msg.data[1:-1])

	def bootstrap(self, crp, timeout=60, ui_cb=lambda:None):
		if(len(crp.chunks)<2):
			raise CRP08_exception("CRP file is empty!")
		crp_chunk_i = 1
		self.open_can(crp.chunks[crp_chunk_i])
		self.p.log("Power On ECU, please! (within "+str(timeout)+"sec.)")
		while(True):
			cmd, data = self.recv(timeout, ui_cb)
			# Hello
			if(cmd == 0x0A):
				self.p.log("ECU: Hello")
				crp_chunk_i = 1
				self.p.progress_start(len(crp.chunks[crp_chunk_i].data))
				self.open_can(crp.chunks[crp_chunk_i])
				self.send_start()
			# Frame request
			if(cmd == 0x01):
				frame_id = int.from_bytes(data[4:6], BO_BE)
				#self.p.log("ECU: Request Frame "+str(frame_id))
				if(frame_id > 0): self.p.progress(self.frame_size)
				self.send_frame(crp.chunks[crp_chunk_i].data, frame_id)
			# Erase Info
			if(cmd == 0x03):
				self.p.log("ECU: Erasing...")
				self.p.progress(self.frame_size)
			# Programming Info
			if(cmd == 0x02):
				self.p.progress_end()
				crp_chunk_i += 1
				if(crp_chunk_i < len(crp.chunks)):
					self.p.log("ECU: Next chunk!")
					self.p.progress_start(len(crp.chunks[crp_chunk_i].data))
					self.open_can(crp.chunks[crp_chunk_i])
					self.send_start()
				else:
					self.p.log("ECU: Programming completed!")
					break
			# Error
			if(cmd == 0x04 or cmd == 0x05):
				error = data[4]
				raise CRP08_exception("ECU: Error "+hex(error)+" "+self.errors.get(error, "Unknow"))
		self.close_can()

if __name__ == "__main__":
	print("CRP Uploader for T4e/T6 Black ECU\n")
	ap = argparse.ArgumentParser()
	ap.add_argument(
		"-i",
		"--interface",
		required=False,
		type=str,
		help="The CAN-Bus interface to use.",
		default="socketcan"
	)
	ap.add_argument(
		"-d",
		"--device",
		required=False,
		type=str,
		help="The CAN-Bus device to use.",
		default="can0"
	)
	ap.add_argument(
		"-f",
		"--file",
		required=True,
		type=str,
		help="The CRP file to upload"
	)
	args = vars(ap.parse_args())
	can_if = args['interface']
	can_ch = args['device']
	crp_file = args['file']

	crp = CRP08()
	crp.read_file(crp_file, None)
	up = CRP08_uploader(can_if, can_ch, Progress())
	try:
		up.bootstrap(crp)
	finally:
		up.close_can()

