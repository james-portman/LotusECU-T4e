import os, time

class Progress:
	# Override it if needed
	def log(self, msg):
		print(msg)

	# Override it if needed
	def progress_start(self, total_size):
		pass

	# Override it if needed
	def progress(self, chunk_size):
		print(".", end="", flush=True)

	# Override it if needed
	def progress_end(self):
		print()

class FileProgressException(Exception):
	pass

class FileProgress(Progress):
	def __aligned(self, size, chunk_size, chunk_align):
		if(size % chunk_size != 0 and chunk_align):
			raise FileProgressException("File size is not a multiple of "+str(chunk_size))

	def download(self, address, size, filename, read_fnct, chunk_size, chunk_align):
		self.log("Download "+str(size)+" bytes @ "+hex(address)+" into "+filename)
		self.__aligned(size, chunk_size, chunk_align)
		with open(filename,'wb') as f:
			self.progress_start(size)
			while(size > 0):
				if(chunk_align):
					chunk = read_fnct(address)
				else:
					chunk_size = min(chunk_size, size)
					chunk = read_fnct(address, chunk_size)
				f.write(chunk)
				self.progress(chunk_size)
				address += chunk_size
				size -= chunk_size
			self.progress_end()

	def verify(self, address, filename, read_fnct, chunk_size, chunk_align, offset=0, size=None):
		if(not size): size = os.path.getsize(filename) - offset
		self.log("Verify "+str(size)+" bytes @ "+hex(address)+" from "+filename+" +"+hex(offset))
		self.__aligned(size, chunk_size, chunk_align)
		with open(filename,'rb') as f:
			f.seek(offset)
			self.progress_start(size)
			while(size > 0):
				if(chunk_align):
					chunk = read_fnct(address)
				else:
					chunk_size = min(chunk_size, size)
					chunk = read_fnct(address, chunk_size)
				f_chunk = f.read(chunk_size)
				if(f_chunk != chunk):
					raise FileProgressException("Verify failed! @ "+hex(address))
				self.progress(chunk_size)
				address += chunk_size
				size -= chunk_size
			self.progress_end()

	def verify_blank(self, address, size, read_fnct, chunk_size, chunk_align):
		self.log("Verify Blank "+str(size)+" bytes @ "+hex(address))
		self.__aligned(size, chunk_size, chunk_align)
		self.progress_start(size)
		while(size > 0):
			if(chunk_align):
				chunk = read_fnct(address)
			else:
				chunk_size = min(chunk_size, size)
				chunk = read_fnct(address, chunk_size)
			for byte in chunk:
				if(byte != 0xFF):
					raise FileProgressException("Verify Blank failed! @ "+hex(address))
			self.progress(chunk_size)
			address += chunk_size
			size -= chunk_size
		self.progress_end()

	def upload(self, address, filename, write_fnct, chunk_size, chunk_align, offset=0, size=None):
		if(not size): size = os.path.getsize(filename) - offset
		self.log("Upload "+str(size)+" bytes @ "+hex(address)+" from "+filename+" +"+hex(offset))
		self.__aligned(size, chunk_size, chunk_align)
		with open(filename,'rb') as f:
			f.seek(offset)
			self.progress_start(size)
			while(size > 0):
				chunk_size = min(chunk_size, size)
				chunk = f.read(chunk_size)
				write_fnct(address, chunk)
				self.progress(chunk_size)
				address += chunk_size
				size -= chunk_size
			self.progress_end()

	def watch(self, address, filename, write_fnct, offset=0, size=None, ui_cb=lambda:None):
		if(not size): size = os.path.getsize(filename) - offset
		self.log("Watch "+str(size)+" bytes @ "+hex(address)+" from "+filename+" +"+hex(offset))
		cache_ts = os.path.getmtime(filename)
		with open(filename, 'rb') as f:
			f.seek(offset)
			cache_data = f.read(size)
		p=0
		while(True):
			ui_cb()
			if(p == 0):
				self.progress_start(16)
				p = 16
			else:
				self.progress(1)
				p -= 1
			time.sleep(0.5)
			ts = os.path.getmtime(filename)
			if(cache_ts != ts):
				with open(filename, 'rb') as f:
					f.seek(offset)
					data = f.read(size)
				i = 0
				while(i < min(len(cache_data),len(data))):
					j = i
					while(cache_data[j] != data[j]): j += 1
					if(j > i):
						self.log("Update "+str(j-i)+" bytes @ "+hex(i))
						write_fnct(address+i, data[i:j])
					i = j + 1
				cache_ts = ts
				cache_data = data
		self.progress_end()

if __name__ == "__main__":
	print("Library to upload/download/verify files.")

