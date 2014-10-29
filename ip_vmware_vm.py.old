from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim, vmodl
import time
import sys

if len(sys.argv) != 6:
	print "Usage: "
	print "python ip_vmware_vm.py <vmware_server> <vm_name> <network_interface> <ip_address> <gateway>"
	sys.exit(1)

vmware_datacenter = sys.argv[1]
vmname = sys.argv[2]
vm_ip = sys.argv[3]
gateway = sys.argv[4]

if vmware_datacenter == 'dc1': vmware_server = 'server1'
if vmware_datacenter == 'dc2': vmware_server = 'server2'
if vmware_datacenter == 'dc3': vmware_server = 'server3'

interface = "eth0"

def find_vm(si,name):
	content = si.content
	obj_view = content.viewManager.CreateContainerView(content.rootFolder,[vim.VirtualMachine],True)
	vm_list = obj_view.view
	for vm in vm_list:
		if vm.name == name:
			return vm
	return None

def create_program_spec(path, arguments):
    prog = vim.vm.guest.ProcessManager.ProgramSpec()
    prog.programPath = path
    prog.arguments = ' '.join(arguments)
    return prog

print 'Connecting to VI Server...'
si = SmartConnect(host=vmware_server,user="user",pwd="pass",port=443)
vm = find_vm(si,vmname)

print 'Checking for ze powers....'
if vm.summary.runtime.powerState != "poweredOn":
	vm.PowerOn()
	print "Waiting 60 seconds for server to power on"
	time.sleep(60)
	vm = find_vm(si,vmname)
	if vm.summary.runtime.powerState != "poweredOn":
		print "Unable to power on server: " + vmname
		sys.exit(2)

print 'Doing the things...'
first_3_octets = vm_ip[0:vm_ip.rfind(".")]
creds = vim.vm.guest.NamePasswordAuthentication(username='root', password='g0tsh0t3')
proc_manager = si.content.guestOperationsManager.processManager
proc_manager.StartProgramInGuest(vm=vm,auth=creds,spec=create_program_spec("/bin/hostname",[vmname]))
proc_manager.StartProgramInGuest(vm=vm,auth=creds,spec=create_program_spec("/sbin/ifconfig",[interface,vm_ip, "netmask", "255.255.255.0", "up"]))
proc_manager.StartProgramInGuest(vm=vm,auth=creds,spec=create_program_spec("/sbin/route",['add','default','gw',first_3_octets + ".1",interface]))
proc_manager.StartProgramInGuest(vm=vm,auth=creds,spec=create_program_spec("/bin/cp",['/etc/resolv.conf.prod','/etc/resolv.conf']))
proc_manager.StartProgramInGuest(vm=vm,auth=creds,spec=create_program_spec("/bin/mkdir",['-p', 'dir']))
proc_manager.StartProgramInGuest(vm=vm,auth=creds,spec=create_program_spec("/bin/mkdir",['-p', 'dir2']))
if vmware_datacenter == "polaris":
    proc_manager.StartProgramInGuest(vm=vm,auth=creds,spec=create_program_spec("/bin/mount",['source', 'dest']))
    proc_manager.StartProgramInGuest(vm=vm,auth=creds,spec=create_program_spec("/bin/mount",['source2', 'dest2']))
elif vmware_datacenter == "orion":
    proc_manager.StartProgramInGuest(vm=vm,auth=creds,spec=create_program_spec("/bin/mount",['source', 'dest']))
    proc_manager.StartProgramInGuest(vm=vm,auth=creds,spec=create_program_spec("/bin/mount",['source2', 'dest2']))
elif vmware_datacenter == 'nexus':
    proc_manager.StartProgramInGuest(vm=vm,auth=creds,spec=create_program_spec("/bin/mount",['source', 'dest']))
    proc_manager.StartProgramInGuest(vm=vm,auth=creds,spec=create_program_spec("/bin/mount",['source2', 'dest2']))
else:
    "I don't know how you got here. Datacenter not defined correctly. Unable to run mount commands"

if vm_osver == "6":
    print "Running OEL 6 specific commands"
if vm_osver == "5":
    print "Running OEL 5 specific commands"
    proc_manager.StartProgramInGuest(vm=vm,auth=creds,spec=create_program_spec('/usr/bin/yum',['--enablerepo=*', '--nogpgcheck', '-y', 'install', 'pkgconfig', '/nfs/infra/3rd_party/sw/virt-what-1.11-2.el5.x86_64.rpm']))

print "Successfully ran commands against vm."

print 'Done!'
