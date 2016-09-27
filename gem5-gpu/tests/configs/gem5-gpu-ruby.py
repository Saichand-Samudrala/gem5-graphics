# Copyright (c) 2006-2008 The Regents of The University of Michigan
# Copyright (c) 2012-2013 Mark D. Hill and David A. Wood
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met: redistributions of source code must retain the above copyright
# notice, this list of conditions and the following disclaimer;
# redistributions in binary form must reproduce the above copyright
# notice, this list of conditions and the following disclaimer in the
# documentation and/or other materials provided with the distribution;
# neither the name of the copyright holders nor the names of its
# contributors may be used to endorse or promote products derived from
# this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# Authors: Joel Hestness, Jason Power

import optparse
import os
import sys
from os.path import join as joinpath

import m5
from m5.defines import buildEnv
from m5.objects import *
from m5.util import addToPath, fatal

def getTestFilename(test_location):
    file_chop_index = test_location.find('tests/')
    if file_chop_index <= 0:
        fatal('test_filename lacks \'tests\/\' substring')
    test_filename = test_location[file_chop_index:]
    test_filename = test_filename.replace('/opt/','/')
    test_filename = test_filename.replace('/debug/','/')
    test_filename = test_filename.replace('/fast/','/')
    isa = 'x86'
    if not isa in test_filename:
        fatal('ISA of this test is not supported')

    file_chop_index = test_filename.find('%s/' % isa)
    if file_chop_index >= len(test_filename):
        fatal('test_filename lacks \'%s\/\' substring' % isa)
    test_filename = test_filename[:file_chop_index]

    test_filename = os.path.join(test_filename, 'test.py')
    if not os.path.exists(test_filename):
        fatal('Could not find test script: \'%s\'' % test_filename)
    return test_filename


addToPath('../configs/common')
addToPath('../configs/ruby')
addToPath('../configs/topologies')
addToPath('../../gem5-gpu/configs')
addToPath('../../gem5-gpu/configs/gpu_protocol')

import GPUConfig
import GPUMemConfig
import Options
import Ruby
import Simulation

parser = optparse.OptionParser()
GPUConfig.addGPUOptions(parser)
GPUMemConfig.addMemCtrlOptions(parser)
Options.addCommonOptions(parser)
Options.addSEOptions(parser)

#
# Add the ruby specific and protocol specific options
#
Ruby.define_options(parser)

(options, args) = parser.parse_args()

options.ruby = True
options.g_depth_shader=1 #z-unit not used

if not args or len(args) != 1:
    print "Error: script expects a single positional argument"
    sys.exit(1)

if buildEnv['TARGET_ISA'] != "x86":
    fatal("gem5-gpu doesn't currently work with non-x86 system!")

#
# Setup test benchmark to be run
#

# Get the filename of the test
test_filename = getTestFilename(args[0])

# Load the test information from the file
execfile(test_filename)

#
# CPU type configuration
#
if options.cpu_type != "timing" and options.cpu_type != "detailed":
    print "Warning: gem5-gpu only works with timing and detailed CPUs. Defaulting to timing"
    options.cpu_type = "timing"
(CPUClass, test_mem_mode, FutureClass) = Simulation.setCPUClass(options)

#
# Memory space configuration
#
(cpu_mem_range, gpu_mem_range) = GPUConfig.configureMemorySpaces(options)

# Hard code the cache block width to 128B for now
# TODO: Remove this if/when block size can be different than 128B
if options.cacheline_size != 128:
    print "Warning: Only block size currently supported is 128B. Defaulting to 128."
    options.cacheline_size = 128

#
# Instantiate system
#
system = System(cpu = [CPUClass(cpu_id = i)
                       for i in xrange(options.num_cpus)],
                mem_mode = test_mem_mode,
                mem_ranges = [cpu_mem_range],
                cache_line_size = options.cacheline_size)

# Create a top-level voltage domain
system.voltage_domain = VoltageDomain(voltage = options.sys_voltage)

# Create a source clock for the system and set the clock period
system.clk_domain = SrcClockDomain(clock = options.sys_clock,
                                   voltage_domain = system.voltage_domain)

# Create a CPU voltage domain
system.cpu_voltage_domain = VoltageDomain()

# Create a separate clock domain for the CPUs
system.cpu_clk_domain = SrcClockDomain(clock = options.cpu_clock,
                                       voltage_domain =
                                       system.cpu_voltage_domain)

mem_ctrls = [SimpleMemory(range = cpu_mem_range)]
system.mem_ctrls = mem_ctrls

Simulation.setWorkCountOptions(system, options)

#
# Create the GPU
#
system.gpu = GPUConfig.createGPU(options, gpu_mem_range)

if options.split:
    system.gpu_physmem = SimpleMemory(range = gpu_mem_range)
    system.mem_ranges.append(gpu_mem_range)

#
# Setup Ruby
#
system.ruby_clk_domain = SrcClockDomain(clock = options.ruby_clock,
                                        voltage_domain = system.voltage_domain)
Ruby.create_system(options, system)

system.gpu.ruby = system.ruby
system.ruby.clk_domain = system.ruby_clk_domain

#
# Connect CPU ports
#
for (i, cpu) in enumerate(system.cpu):
    ruby_port = system.ruby._cpu_ports[i]

    cpu.clk_domain = system.cpu_clk_domain
    cpu.createThreads()
    cpu.createInterruptController()
    #
    # Tie the cpu ports to the correct ruby system ports
    #
    cpu.icache_port = system.ruby._cpu_ports[i].slave
    cpu.dcache_port = system.ruby._cpu_ports[i].slave
    cpu.itb.walker.port = system.ruby._cpu_ports[i].slave
    cpu.dtb.walker.port = system.ruby._cpu_ports[i].slave
    if buildEnv['TARGET_ISA'] == "x86":
        cpu.interrupts.pio = ruby_port.master
        cpu.interrupts.int_master = ruby_port.slave
        cpu.interrupts.int_slave = ruby_port.master

    system.ruby._cpu_ports[i].access_phys_mem = True

#
# Connect GPU ports
#
GPUConfig.connectGPUPorts(system.gpu, system.ruby, options)

GPUMemConfig.setMemoryControlOptions(system, options)

#
# Finalize setup and benchmark, and then run
#
root = Root(full_system = False, system = system)

command_line = []
command_line.append(options.cmd)
for option in options.options.split():
    command_line.append(option)
root.system.cpu[0].workload = LiveProcess(cmd = command_line,
                                          executable = binpath(options.cmd))
if root.system.cpu[0].checker != NULL:
    root.system.cpu[0].checker.workload = root.system.cpu[0].workload

m5.disableAllListeners()

Simulation.run(options, root, system, FutureClass)
