import sys
import time
from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim, vmodl
import random

if len(sys.argv) != 8:
    print "Usage: "
    print "python create_vm_pyvmomi.py <polaris|orion|nexus> <vm_cluster> <vm_name> <cpus> <memory_in_GB> <IP> <5|6>"
    sys.exit(1)

vmware_server = sys.argv[1].lower()
vm_cluster = sys.argv[2].upper()
vm_name = sys.argv[3].lower()
vm_CPUs = sys.argv[4]
vm_memory = sys.argv[5]
vm_ip = sys.argv[6]
vm_osver = sys.argv[7]



if not (vm_osver == '5' or vm_osver == '6'):
    print "Invalid OS version requested. Please use 5 for OEL 5.5 and 6 for OEL 6.1+"
    exit(3)

try:
    cpu_val = int(vm_CPUs)
    if cpu_val < 1 or cpu_val > 8:
        print "CPUs must be between 1 and 8"
        sys.exit(2)
    vm_CPUs = cpu_val
except ValueError:
    print "CPUs must be an integer between 1 and 8"

try:
    mem_val = int(vm_memory)
    if mem_val < 1 or mem_val > 64:
        print "Memory must be between 1 and 64 GB"
        sys.exit(2)
    vm_memory = mem_val
except ValueError:
    print "Memory must be an integer between 1 and 64"

si = SmartConnect(host=vmware_server,user="Username",pwd="password",port=443)

template = None


def find_datastore(si,name):
  content = si.content
  obj_view = content.viewManager.CreateContainerView(content.rootFolder,[vim.StoragePod],True)
  ds_list = obj_view.view
  obj_view.Destroy()
  for ds in ds_list:
    if ds.name == name:
      return ds
  return None

def find_vm(si,name):
	content = si.content
	obj_view = content.viewManager.CreateContainerView(content.rootFolder,[vim.VirtualMachine],True)
	vm_list = obj_view.view
	for vm in vm_list:
		if vm.name == name:
			return vm
	return None

def find_cluster(si,name):
    content = si.content
    obj_view = content.viewManager.CreateContainerView(content.rootFolder,[vim.ClusterComputeResource],True)
    cluster_list = obj_view.view
    obj_view.Destroy()
    for cluster in cluster_list:
        if cluster.name == name:
            return cluster
    return None

def find_resource_pool(si,name):
    content = si.content
    obj_view = content.viewManager.CreateContainerView(content.rootFolder,[vim.ResourcePool],True)
    rp_list = obj_view.view
    obj_view.Destroy()
    for rp in rp_list:
        if rp.parent.name == name:
            return rp
    return None

def find_network(si,cluster, first_3_octets):
    cluster_name = cluster.name
    print "Finding network on cluster {cluster_name} with ip starting with {first_3_octets}".format(**locals())
    for network in cluster.network:
        if first_3_octets in network.name:
            return network
    print "Found network %s" % network.name
    return None

def find_folder(si,name):
    content = si.content
    obj_view = content.viewManager.CreateContainerView(content.rootFolder,[vim.Folder],True)
    folder_list = obj_view.view
    obj_view.Destroy()
    for folder in folder_list:
        if folder.name == name:
            return folder
    return None

def find_folder_in_folder(folder,foldername):
    for f in folder.childEntity:
        if f.name == foldername:
            return f
    return None


def find_virtual_nic(vm):
    for device in vm.config.hardware.device:
        if isinstance(device, vim.vm.device.VirtualEthernetCard):
            return device
    return None

def get_vm_nic(vm):
    for device in vm.config.hardware.device:
        if isinstance(device, vim.vm.device.VirtualEthernetCard):
            return device
    return None

def get_datastore(cluster):
    cluster_name = cluster.name
    print "Finding datastore on cluster {cluster_name} with most free space".format(**locals())
    datastore = 60 * 1024 * 1024
    for ds in cluster.datastore:
        if cluster.name in ds.name:
            freespace = ds.summary.freeSpace
            if freespace > datastore and ds.summary.accessible == True:
                datastore = ds
    datastore_name = datastore.name
    print "Found datastore {datastore_name}".format(**locals())
    return datastore


def create_nic_spec(template,cluster,first_3_octets):
    pg_obj = find_network(si,cluster,first_3_octets)
    nicspec = vim.vm.device.VirtualDeviceSpec()
    nicspec.operation = vim.vm.device.VirtualDeviceSpec.Operation.edit
    nicspec.device = get_vm_nic(template_vm)
    nicspec.device.backing = vim.vm.device.VirtualEthernetCard.DistributedVirtualPortBackingInfo()
    dvs_port_connection = vim.dvs.PortConnection()
    dvs_port_connection.portgroupKey= pg_obj.key
    dvs_port_connection.switchUuid= pg_obj.config.distributedVirtualSwitch.uuid
    nicspec.device.backing.port = dvs_port_connection
    nicspec.device.connectable = vim.vm.device.VirtualDevice.ConnectInfo()
    nicspec.device.connectable.startConnected = True
    nicspec.device.connectable.allowGuestControl = True
    return nicspec

def create_disk(cluster):
    datastore = get_datastore(cluster)
    diskspec = vim.vm.device.VirtualDeviceSpec()
    diskspec.operation = vim.vm.device.VirtualDeviceSpec.Operation.add
    diskspec.fileOperation = vim.vm.device.VirtualDeviceSpec.FileOperation.create
    #Create Disk Backing
    disk_backing = vim.vm.device.VirtualDisk.FlatVer2BackingInfo()
    disk_backing.thinProvisioned = True
    disk_backing.diskMode = vim.vm.device.VirtualDiskOption.DiskMode.persistent
    disk_backing.fileName = "[" + datastore.name + "]"
    disk_backing.datastore = datastore
    #Create Disk
    disk = vim.vm.device.VirtualDisk()
    disk.key = 1
    disk.backing = disk_backing
    disk.capacityInKB = 200 * 1024 * 1024
    disk.controllerKey = 1
    disk.unitNumber = 0
    diskspec.device = disk
    return diskspec

def create_scsi_ctrl():
    ctrlspec = vim.vm.device.VirtualDeviceSpec()
    ctrlspec.operation = vim.vm.device.VirtualDeviceSpec.Operation.add
    # Create Controller
    ctlr = vim.vm.device.ParaVirtualSCSIController()
    ctlr.key = 1
    ctlr.sharedBus = vim.vm.device.VirtualSCSIController.Sharing.noSharing
    ctlr.busNumber = 1
    ctrlspec.device = ctlr
    return ctrlspec

def WaitTask(task, actionName='job', hideResult=False):
    while task.info.state == vim.TaskInfo.State.running:
        time.sleep(2)

    if task.info.state == vim.TaskInfo.State.success:
        if task.info.result is not None and not hideResult:
            out = '%s completed successfully, result: %s' % (actionName, task.info.result)
        else:
            out = '%s completed successfully.' % actionName
        print out
    else:
        out = "%s did not complete successfully: %s" % (actionName, task.info.error)
        print out
        raise task.info.error
    return task.info.result

def create_program_spec(path, arguments):
    prog = vim.vm.guest.ProcessManager.ProgramSpec()
    prog.programPath = path
    prog.arguments = ' '.join(arguments)
    return prog


print "Finding appropriate VM template for OEL %s" % vm_osver
interface = None
if vm_osver == "6":
  template_vm = find_vm(si,"6-template")
elif vm_osver == "5":
  template_vm = find_vm(si,"5-template")
else:
  print "Unable to determine template to use. exiting..."
  sys.exit(3)

print "Found template %s" % template_vm.name


hostname = vm_name.lower()
application = hostname[3:7].upper()
cluster = find_cluster(si,vm_cluster)
if cluster == None:
    print "Unable to find cluster named %s" % vm_cluster
    sys.exit(5)

print "Found cluster using provided cluster name"
first_3_octets = vm_ip[0:vm_ip.rfind(".")]

# add and modify the hardware
devices = []
devices.append(create_nic_spec(template_vm,cluster,first_3_octets))
devices.append(create_scsi_ctrl())
devices.append(create_disk(cluster))

config_spec = vim.vm.ConfigSpec(memoryMB=vm_memory * 1024,numCPUs=vm_CPUs,deviceChange=devices)
resource_pool = find_resource_pool(si,cluster.name)
# AutoCreatedVMS is found under 9. Linux. All vm's created by this script will be placed in a folder under it.
root_folder = find_folder(si,"AutoCreatedVMS")
root_folder_name = root_folder.name
print "Looking for folder {application} in {root_folder_name}".format(**locals())
folder_name = find_folder_in_folder(root_folder,application)
folder = None
if folder_name == None:
    print "Unable to find folder {application}, creating it in {root_folder_name} and placing VM.".format(**locals())
    folder = root_folder.CreateFolder(application)
else:
    print "Found existing folder: {application}. Placing VM in folder.".format(**locals())
    folder = folder_name
ds = get_datastore(cluster)
relocate_spec = vim.vm.RelocateSpec(pool=resource_pool,datastore=ds)
clone_spec = vim.vm.CloneSpec(powerOn=True,template=False,location=relocate_spec, config=config_spec)
create_task = template_vm.Clone(name=hostname,folder=folder,spec=clone_spec)
print "Creating VM and waiting for task to complete."
result = WaitTask(create_task, 'Create VM %s' % hostname)

print "waiting 1 minute for OS to boot"
time.sleep(60)

creds = vim.vm.guest.NamePasswordAuthentication(username='templateuser', password='templatepass')
vm = find_vm(si,hostname)
print "Connecting to {hostname} to configure..".format(**locals())
proc_manager = si.content.guestOperationsManager.processManager
proc_manager.StartProgramInGuest(vm=vm,auth=creds,spec=create_program_spec("/bin/hostname",[hostname]))
proc_manager.StartProgramInGuest(vm=vm,auth=creds,spec=create_program_spec("/sbin/ifconfig",[interface,vm_ip, "netmask", "255.255.255.0", "up"]))
proc_manager.StartProgramInGuest(vm=vm,auth=creds,spec=create_program_spec("/sbin/route",['add','default','gw',first_3_octets + ".1",interface]))
proc_manager.StartProgramInGuest(vm=vm,auth=creds,spec=create_program_spec("/bin/cp",['/etc/resolv.conf.prod','/etc/resolv.conf']))
proc_manager.StartProgramInGuest(vm=vm,auth=creds,spec=create_program_spec("/bin/mkdir",['-p', '/nfs/infra']))
proc_manager.StartProgramInGuest(vm=vm,auth=creds,spec=create_program_spec("/bin/mkdir",['-p', '/depot/linux_x86']))
proc_manager.StartProgramInGuest(vm=vm,auth=creds,spec=create_program_spec("/bin/mount",['placetomount', 'folder']))
proc_manager.StartProgramInGuest(vm=vm,auth=creds,spec=create_program_spec("/bin/mount",['placetomount', 'folder']))

if vm_osver == "6":
    print "Running OEL 6 specific commands"
if vm_osver == "5":
    print "Running OEL 5 specific commands"
    proc_manager.StartProgramInGuest(vm=vm,auth=creds,spec=create_program_spec('/usr/bin/yum',['--enablerepo=*', '--nogpgcheck', '-y', 'install', 'pkgconfig', '/nfs/infra/3rd_party/sw/virt-what-1.11-2.el5.x86_64.rpm']))

print "Successfully ran commands against vm."








