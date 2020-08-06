#!/usr/bin/python3

import sys
import os
import re
import copy

class SliceData:
	def __init__(self):
		self.reg_int = []
		self.reg_float= []
		self.stack_data = []
		self.stack_base = 0
		self.stack_max_size = 0
		self.stack_sp_top = 0
		self.stack_sp_bottom = 0
		self.vma_list_start = []
		self.vma_list_end = []
		self.vma_list_name = []
		self.mem_init_addr = []
		self.mem_init_data = []

	def printOut(self):
		for i in range(0, len(self.reg_int)):
			print("reg_int " + str(i) + " " + hex(self.reg_int[i]))
		for i in range(0, len(self.reg_float)):
			print("reg_float " + str(i) + " " + hex(self.reg_float[i]))
		print("stack_base " + hex(self.stack_base))
		print("stack_sp_top " + hex(self.stack_sp_top))
		print("stack_sp_bottom " + hex(self.stack_sp_bottom))
		for i in range(0, len(self.stack_data)):
			print("stack_data " + str(i) + " " + hex(self.stack_data[i]))
		for i in range(0, len(self.vma_list_name)):
			print("vma " + str(i) + " " + self.vma_list_name[i] + " " \
					+ hex(self.vma_list_start[i]) + " " + hex(self.vma_list_end[i]) \
					+ " " + hex(self.vma_list_end[i] - self.vma_list_start[i]))
		for i in range(0, len(self.mem_init_addr)):
			print("mem " + str(i) + " " + hex(self.mem_init_addr[i]) + " " + hex(self.mem_init_data[i]))

class SliceParse:
	'''Parse a slice output by Gem5 and give target source codes'''

	FLAG_START_REG_INT= "simpoint_reg_int:"
	FLAG_START_REG_FLOAT = "simpoint_reg_float:"
	FLAG_START_STACK_DATA = "simpoint_stack_top:"
	FLAG_START_VMA_LIST = "/* VMA list */"
	FLAG_START_MEM_INIT = "/* Address-Value pairs */"
	FLAG_START_TEXT = "/* SimPoint Start */"
	FLAG_STOP_TEXT = "/* SimPoint Exit */"

	RELOCATE_CHECK_MASK = 0xFFFFFFFF00000000

	VMA_ALIGN = 0x1000
	VMA_MASK_BASE = 0xFFFFFFFFFFFFFFFF ^ (VMA_ALIGN - 1)

	def __init__(self, slice_fd):
		self.slice_fd = slice_fd
		self.slice_data = SliceData()
		self.slice_data_update = SliceData()
		self.slice_text = []

	def parse_reg_int(self):
		slice_fd = self.slice_fd
		data_list = []
		while (True):
			slice_line = slice_fd.readline()
			if (not slice_line):
				break
			slice_line = slice_line.strip('\n')
			line_words = slice_line.split(' ')
			if (len(line_words) < 6):
				break
			if (line_words[4] != ".dword"):
				break
			data_list.append(int(line_words[5], 16))
		self.slice_data.reg_int = data_list

	def parse_reg_float(self):
		self.slice_data.reg_float = []
	
	def parse_stack(self):
		slice_fd = self.slice_fd
		# Stack data is at the begining
		data_list = []
		while (True):
			slice_line = slice_fd.readline()
			if (not slice_line):
				break
			slice_line = slice_line.strip('\n')
			line_words = slice_line.split(' ')
			if (len(line_words) < 6):
				break
			if (line_words[4] != ".dword"):
				break
			data_list.append(int(line_words[5], 16))
		self.slice_data.stack_data = data_list

		# The following is other information of format #define
		while (True):
			slice_line = slice_fd.readline()
			if (not slice_line):
				break	
			slice_line = slice_line.strip('\n')
			if (len(slice_line) == 0):
				break
			line_words = slice_line.split(' ')
			if (len(line_words) != 3):
				continue
			if (line_words[0] != "#define"):
				continue
			if (line_words[1] == "SIMPOINT_STACK_BASE"):
				self.slice_data.stack_base = int(line_words[2], 16)
			elif (line_words[1] == "SIMPOINT_STACK_MAX_SIZE"):
				self.slice_data.stack_max_size = int(line_words[2], 16)
			elif (line_words[1] == "SIMPOINT_STACK_SP_TOP"):
				self.slice_data.stack_sp_top = int(line_words[2], 16)
			elif (line_words[1] == "SIMPOINT_STACK_SP_BOTTOM"):
				self.slice_data.stack_sp_bottom = int(line_words[2], 16)

	def parse_vma_list(self):
		slice_fd = self.slice_fd
		while (True):
			slice_line = slice_fd.readline()
			if (not slice_line):
				break
			slice_line = slice_line.strip('\n')
			line_words = slice_line.split(' ')
			if (len(line_words) != 6):
				break
			sub_words = line_words[0].split('-')
			if (len(sub_words) != 2):
				break
			if (len(line_words[5]) < 3): # Min. VMA name is "[?]"
				break
			vma_start = int("0x" + sub_words[0], 16)
			vma_end = int("0x" + sub_words[1], 16)
			vma_name = line_words[5][1:-1]
			self.append_new_vma(vma_start, vma_end, vma_name)
	
	def append_new_vma(self, start, end, name):
		self.slice_data.vma_list_start.append(start)
		self.slice_data.vma_list_end.append(end)
		self.slice_data.vma_list_name.append(name)

	def find_addr_in_vma(self, addr):
		for i in range(0, len(self.slice_data.vma_list_name)):
			if (addr >= self.slice_data.vma_list_start[i] and addr < self.slice_data.vma_list_end[i]):
				return True
		return False

	def add_vma(self):
		for addr in self.slice_data.mem_init_addr:
			if (self.find_addr_in_vma(addr)):
				continue
			vma_start = addr & self.VMA_MASK_BASE
			vma_end = vma_start + self.VMA_ALIGN
			vma_name = "added"
			self.append_new_vma(vma_start, vma_end, vma_name)

	def parse_mem_init(self):
		slice_fd = self.slice_fd
		while (True):
			slice_line = slice_fd.readline()
			if (not slice_line):
				break
			slice_line = slice_line.strip('\n')
			line_words = slice_line.split(' ')
			if (len(line_words) != 2):
				break
			self.slice_data.mem_init_addr.append(int(line_words[0], 16))
			self.slice_data.mem_init_data.append(int(line_words[1], 16))

	def parse_text_line(self, slice_line):
		#
		# Replace '_' with '.' in instruction mnemonic.
		#
		if (len(slice_line) <= 0):
			output_line = slice_line
		elif (slice_line[0] == '#' or slice_line[0] == '/'):
			output_line = slice_line
		elif (':' in slice_line):
			output_line = slice_line
		else:
			mnemonic = slice_line.split(' ')[0]
			underscore_cnt = mnemonic.count('_')
			output_line = slice_line.replace('_', '.', underscore_cnt)
		self.slice_text.append(output_line)

	def parse(self):
		slice_fd = self.slice_fd
		while (True):
			slice_line = slice_fd.readline()
			if (not slice_line):
				break
			slice_line = slice_line.strip('\n')

			if (len(slice_line) <= 0):
				continue
			elif (slice_line.find(self.FLAG_START_REG_INT) == 0):
				print("Dectecting register integer...")
				self.parse_reg_int()
				continue
			elif (slice_line.find(self.FLAG_START_REG_FLOAT) == 0):
				print("Dectecting register float...")
				self.parse_reg_float()
				continue
			elif (slice_line.find(self.FLAG_START_STACK_DATA) == 0):
				print("Dectecting stack...")
				self.parse_stack()
				continue
			elif (slice_line.find(self.FLAG_START_VMA_LIST) == 0):
				print("Dectecting VMA list...")
				self.parse_vma_list()
				continue
			elif (slice_line.find(self.FLAG_START_MEM_INIT) == 0):
				print("Dectecting memory initial...")
				self.parse_mem_init()
				continue
			else:
				self.parse_text_line(slice_line)
				continue

	def addr_check_update(self, addr):
		new_addr = addr
		for i in range(0, len(self.slice_data.vma_list_name)):
			if (addr < self.slice_data.vma_list_start[i] or addr >= self.slice_data.vma_list_end[i]):
				continue
			relocate_offset = self.slice_data.vma_list_start[i] - self.slice_data_update.vma_list_start[i]
			if (relocate_offset != 0):
				new_addr -= relocate_offset
				break
		return new_addr

	def reconstruct(self):
		self.add_vma()
		# Make a copy of slice data to make update
		self.slice_data_update = copy.deepcopy(self.slice_data)

		# Build a list of VMA index that need relocate
		vma_cnt = len(self.slice_data.vma_list_name)
		vma_relocate_list = []
		for i in range(0, vma_cnt): 	# First, arrange stack
			if (i in vma_relocate_list):
				continue
			if (self.slice_data.vma_list_name[i] != "stack"):
				continue
			if (not (self.slice_data.vma_list_start[i] & self.RELOCATE_CHECK_MASK)):
				print("WARN: VMA of stack type valid? " + hex(self.slice_data.vma_list_start[i]) + "-" + hex(self.slice_data.vma_list_end[i]))
				continue
			if (not (self.slice_data.vma_list_end[i] & self.RELOCATE_CHECK_MASK)):
				print("WARN: VMA of stack type valid? " + hex(self.slice_data.vma_list_start[i]) + "-" + hex(self.slice_data.vma_list_end[i]))
				continue
			vma_relocate_list.append(i)
		for i in range(0, vma_cnt): 	# Then, others
			if (i in vma_relocate_list):
				continue
			if (not (self.slice_data.vma_list_start[i] & self.RELOCATE_CHECK_MASK) and \
				not (self.slice_data.vma_list_end[i] & self.RELOCATE_CHECK_MASK)):
				continue
			if (not (self.slice_data.vma_list_start[i] & self.RELOCATE_CHECK_MASK) or \
				not (self.slice_data.vma_list_end[i] & self.RELOCATE_CHECK_MASK)):
				print("WARN: VMA of head type valid? " + hex(self.slice_data.vma_list_start[i]) + "-" + hex(self.slice_data.vma_list_end[i]))
				continue
			vma_relocate_list.append(i)

		# Relocate VMA
		# Note: Use 0 start address of free memroy here in internal recording, 
		# while add " + FREE_MEM_BASE" as an offset in ouputing slice.
		mem_free_start = 0
		for i in vma_relocate_list:
			if (self.slice_data.vma_list_name[i] == "stack"):
				vma_size = self.slice_data.stack_max_size
			else:
				vma_size = self.slice_data.vma_list_end[i] - self.slice_data.vma_list_start[i]
			self.slice_data_update.vma_list_start[i] = mem_free_start
			mem_free_start += vma_size
			self.slice_data_update.vma_list_end[i] = mem_free_start

		# Update stack and memory information
		for i in range(0, len(self.slice_data_update.stack_data)):
			self.slice_data_update.stack_data[i] = self.addr_check_update(self.slice_data_update.stack_data[i])
		process_list = []
		process_list.append(self.slice_data_update.stack_data)
		process_list.append(self.slice_data_update.mem_init_addr)
		process_list.append(self.slice_data_update.mem_init_data)
		process_list.append(self.slice_data_update.reg_int)
		for l in process_list:
			for i in range(0, len(l)):
				l[i] = self.addr_check_update(l[i])
		self.slice_data_update.stack_base = self.addr_check_update(self.slice_data_update.stack_base)
		self.slice_data_update.stack_sp_top = self.addr_check_update(self.slice_data_update.stack_sp_top)
		self.slice_data_update.stack_sp_bottom = self.addr_check_update(self.slice_data_update.stack_sp_bottom)

		print("== Slice Data Original ==")
		self.slice_data.printOut()
		print("== Slice Data Updated ==")
		self.slice_data_update.printOut()
		for l in self.slice_text:
			print(l)

	def output(self, output_fd):
		print("Output resulting slice")

		out_str = \
"""\
/*
 * Gem5 Slice
 */

#ifndef FREE_MEM_BASE
#define FREE_MEM_BASE 0x40000000
#endif
"""
		output_fd.write(out_str)

		out_str = \
"""
/* VMA list */
/*
"""
		output_fd.write(out_str)
		for i in range(0, len(self.slice_data_update.vma_list_name)):
			out_str = "VMA " + str(i)
			out_str += " " + self.slice_data_update.vma_list_name[i]
			out_str += " " + hex(self.slice_data_update.vma_list_start[i])
			out_str += " " + hex(self.slice_data_update.vma_list_end[i])
			out_str += " " + hex(self.slice_data_update.vma_list_end[i] - self.slice_data_update.vma_list_start[i])
			out_str += "\n"
			output_fd.write(out_str)
		out_str = \
"""\
 */
"""
		output_fd.write(out_str)

		out_str = \
"""
.global simpoint_entry
.section .text
.balign 4
simpoint_entry:
"""
		output_fd.write(out_str)

		out_str = \
"""
/* Restore normal memory */
"""
		output_fd.write(out_str)
		for i in range(0, len(self.slice_data_update.mem_init_addr)):
			if (self.slice_data_update.mem_init_addr[i] != self.slice_data.mem_init_addr[i]):
				out_str = "li t0, " + hex(self.slice_data_update.mem_init_addr[i]) + " + FREE_MEM_BASE\n"
			else:
				out_str = "li t0, " + hex(self.slice_data.mem_init_addr[i]) + "\n"
			if (self.slice_data_update.mem_init_data[i] != self.slice_data.mem_init_data[i]):
				out_str += "li t1, " + hex(self.slice_data_update.mem_init_data[i]) + " + FREE_MEM_BASE\n"
			else:
				out_str += "li t1, " + hex(self.slice_data.mem_init_data[i]) + "\n"
			out_str += "sd t1, 0(t0)\n"
			output_fd.write(out_str)

		out_str = \
"""
/* Restore stack */
"""
		output_fd.write(out_str)
		out_str = "li t0, " + hex(self.slice_data_update.stack_sp_top) + " + FREE_MEM_BASE\n"
		output_fd.write(out_str)
		for i in range(0, len(self.slice_data_update.stack_data)):
			if (self.slice_data_update.stack_data[i] != self.slice_data.stack_data[i]):
				out_str = "li t1, " + hex(self.slice_data_update.stack_data[i]) + " + FREE_MEM_BASE\n"
			else:
				out_str = "li t1, " + hex(self.slice_data.stack_data[i]) + "\n"
			out_str += "sd t1, " + str(i * 8) + "(t0)\n"
			output_fd.write(out_str)

		out_str = \
"""
/* Restore register - float */
"""
		output_fd.write(out_str)

		out_str = \
"""
/* Restore register - integer */
"""
		output_fd.write(out_str)
		for i in range(0, len(self.slice_data_update.reg_int)):
			if (i == 0): # Register x0 (i.e. register zero) is skipped
				continue
			if (self.slice_data_update.reg_int[i] != self.slice_data.reg_int[i]):
				out_str = "li x" + str(i) + ", " + hex(self.slice_data_update.reg_int[i]) + " + FREE_MEM_BASE\n"
			else:
				out_str = "li x" + str(i) + ", " + hex(self.slice_data.reg_int[i]) + "\n"
			output_fd.write(out_str)
		out_str = "\n"
		output_fd.write(out_str)

		out_str = \
"""
/* Jump to start of slice */
j simpoint_start

/* Full text of slice */
"""
		output_fd.write(out_str)
		text_line_begin = 0
		text_line_end = 0
		for i in range(0, len(self.slice_text)):
			if (self.FLAG_START_TEXT == self.slice_text[i]):
				text_line_begin = i
			if (self.FLAG_STOP_TEXT == self.slice_text[i]):
				text_line_end = i
		for i in range(text_line_begin, text_line_end):
			out_str = self.slice_text[i] + "\n"
			output_fd.write(out_str)

def usage():
		print("Usage:");
		print("    " + sys.argv[0] + " slice-file");

def main():
	if (len(sys.argv) < 2):
		usage()
		sys.exit(2)
		
	slice_file = sys.argv[1]
	print("Open slice file", slice_file)
	try:
		slice_fd = open(slice_file, 'r')
	except IOError:
		print("Failed to open slice file", slice_file)
		sys.exit(2)
	
	output_file = sys.argv[1] + ".S"
	print("Open output file", output_file)
	try:
		output_fd = open(output_file, 'w')
	except IOError:
		print("Failed to open output file", output_file)
		sys.exit(2)
	
	print("Start process")
	parser = SliceParse(slice_fd)
	parser.parse()
	parser.reconstruct()
	parser.output(output_fd)

if __name__== "__main__":
	main()
