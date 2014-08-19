import sys
import time
from pyVim.connect import SmartConnect
from pyVmomi import vim, vmodl
import random


class VmBuilds:
    def connect_to_vmware(self):
        si = SmartConnect(host=self.vmware_server, user=self.vmware_user, pwd=self.vmware_password,
                          port=self.vmware_port)
        return si

    def get_vmware_server(self, datacenter):
        server = None
        if datacenter == 'dc1':
            server = 'server1'
        elif datacenter == 'dc2':
            server = 'server2'
        elif datacenter == 'dc3':
            server = 'server3'
        else:
            print "Hey, did you spell the datacenter name correctly? I don't know where you want me to connect to!"
            sys.exit(666)
        return server

    def find_datastorecluster(self):
        content = self.vmware_connection.content
        obj_view = content.viewManager.CreateContainerView(content.rootFolder, [vim.StoragePod], True)
        ds_list = obj_view.view
        obj_view.Destroy()
        for ds in ds_list:
            if ds.name == self.vm_cluster.name + "_DSC":
                return ds
        return None

    def find_vm(self, name):
        content = self.vmware_connection.content
        obj_view = content.viewManager.CreateContainerView(content.rootFolder, [vim.VirtualMachine], True)
        vm_list = obj_view.view
        for vm in vm_list:
            if vm.name == name:
                return vm
        return None

    def find_cluster(self, name):
        content = self.vmware_connection.content
        obj_view = content.viewManager.CreateContainerView(content.rootFolder, [vim.ClusterComputeResource], True)
        cluster_list = obj_view.view
        obj_view.Destroy()
        for cluster in cluster_list:
            if cluster.name == name:
                return cluster
        return None

    def find_resource_pool(self):
        content = self.vmware_connection.content
        obj_view = content.viewManager.CreateContainerView(content.rootFolder, [vim.ResourcePool], True)
        rp_list = obj_view.view
        obj_view.Destroy()
        for rp in rp_list:
            if rp.parent.name == self.vm_cluster.name:
                return rp
        return None

    def find_network(self):
        cluster_name = self.vm_cluster.name
        first_3_octets = self.vm_ip[0:self.vm_ip.rfind(".")]
        print "Finding network on cluster {cluster_name} with ip starting with {first_3_octets}".format(**locals())
        for network in self.vm_cluster.network:
            if first_3_octets in network.name:
                print "Found network %s" % network.name
                return network
        return None

    def find_folder(self, name):
        content = self.vmware_connection.content
        obj_view = content.viewManager.CreateContainerView(content.rootFolder, [vim.Folder], True)
        folder_list = obj_view.view
        obj_view.Destroy()
        for folder in folder_list:
            if folder.name == name:
                return folder
        return None

    def find_folder_in_folder(self, folder, foldername):
        for f in folder.childEntity:
            if f.name == foldername:
                return f
        return None


    def find_virtual_nic(self, vm):
        for device in vm.config.hardware.device:
            if isinstance(device, vim.vm.device.VirtualEthernetCard):
                return device
        return None

    def get_vm_nic(self, vm):
        for device in vm.config.hardware.device:
            if isinstance(device, vim.vm.device.VirtualEthernetCard):
                return device
        return None

    def get_datastore(self, dscluster):
        dsname = dscluster.name
        print "Finding datastore on cluster {dsname} with most free space".format(**locals())
        base_dsSize = 60 * 1024 * 1024
        for ds in dscluster.childEntity:
            freespace = ds.summary.freeSpace
            if freespace > base_dsSize and ds.summary.accessible == True:
                datastore = ds
        datastore_name = datastore.name
        print "Found datastore {datastore_name}".format(**locals())
        return datastore

# create the nic spec. need to determine if the switch is a standard vm switch or a distributed virtual switch to create the correct backing
    def create_nic_spec(self, template):
        pg_obj = self.find_network()
        if pg_obj == None:
          print "No Network Found"
          exit(2)
        nicspec = vim.vm.device.VirtualDeviceSpec()
        nicspec.operation = vim.vm.device.VirtualDeviceSpec.Operation.edit
        nicspec.device = self.get_vm_nic(template)
        if str(pg_obj.summary.network).find("Distributed") != -1:
          nicspec.device.backing = vim.vm.device.VirtualEthernetCard.DistributedVirtualPortBackingInfo()
          dvs_port_connection = vim.dvs.PortConnection()
          dvs_port_connection.portgroupKey = pg_obj.key
          dvs_port_connection.switchUuid = pg_obj.config.distributedVirtualSwitch.uuid
          nicspec.device.backing.port = dvs_port_connection
        else:
          nicspec.device.backing = vim.vm.device.VirtualEthernetCard.NetworkBackingInfo()
          nicspec.device.backing.network = pg_obj
          nicspec.device.backing.deviceName = pg_obj.name
        nicspec.device.connectable = vim.vm.device.VirtualDevice.ConnectInfo()
        nicspec.device.connectable.startConnected = True
        nicspec.device.connectable.allowGuestControl = True
        return nicspec

    def create_disk(self, disknumber):
        datastorecluster = self.find_datastorecluster()
        datastore = self.get_datastore(datastorecluster)
        diskspec = vim.vm.device.VirtualDeviceSpec()
        diskspec.operation = vim.vm.device.VirtualDeviceSpec.Operation.add
        diskspec.fileOperation = vim.vm.device.VirtualDeviceSpec.FileOperation.create
        # Create Disk Backing
        disk_backing = vim.vm.device.VirtualDisk.FlatVer2BackingInfo()
        disk_backing.thinProvisioned = True
        disk_backing.diskMode = vim.vm.device.VirtualDiskOption.DiskMode.persistent
        disk_backing.fileName = "[" + datastore.name + "]"
        disk_backing.datastore = datastore
        # Create Disk
        disk = vim.vm.device.VirtualDisk()
        disk.key = 1
        disk.backing = disk_backing
        disk.capacityInKB = 200 * 1024 * 1024
        disk.controllerKey = 1
        disk.unitNumber = disknumber
        diskspec.device = disk
        return diskspec

    def create_disks(self):
        print "Creating " + self.vm_diskcount + " disk(s)"
        int_disk = int(self.vm_diskcount)
        disks = []
        if int_disk == 1:
            disks.append(self.create_disk(0))
        elif int_disk == 0:
            return None
        else:
            # python range is not inclusive so range(1,3) returns [1, 2] instead of [1,2,3]. need to add 1 to the diskcount
            for i in range(1, int_disk + 1):
                disks.append(self.create_disk(i - 1))
        return disks

    def create_scsi_ctrl(self, oel_ver):
        ctrlspec = vim.vm.device.VirtualDeviceSpec()
        ctrlspec.operation = vim.vm.device.VirtualDeviceSpec.Operation.add
        # Create Controller
        if oel_ver == 6:
            ctlr = vim.vm.device.ParaVirtualSCSIController()
        else:
            ctlr = vim.vm.device.VirtualLsiLogicSASController()
        ctlr.key = 1
        ctlr.sharedBus = vim.vm.device.VirtualSCSIController.Sharing.noSharing
        ctlr.busNumber = 1
        ctrlspec.device = ctlr
        return ctrlspec

    def WaitTask(self, task, actionName='job', hideResult=False):
        while task.info.state == vim.TaskInfo.State.running:
            time.sleep(2)

        if task.info.state == vim.TaskInfo.State.success:
            if task.info.result is not None and not hideResult:
                out = '%s completed successfully' % actionName
            else:
                out = '%s completed successfully.' % actionName
            print out
        else:
            out = "%s did not complete successfully: %s" % (actionName, task.info.error)
            print out
            raise task.info.error
        return task.info.result

    def create_program_spec(self, path, arguments):
        prog = vim.vm.guest.ProcessManager.ProgramSpec()
        prog.programPath = path
        prog.arguments = ' '.join(arguments)
        return prog

    def Wait_For_Vm_To_Boot(self):
        vm_up = False
        i = 1
        seconds = 120
        while vm_up != True and i < 6:
            print "Waiting %s seconds for OS to boot" % seconds
            time.sleep(seconds)
            if seconds > 10:
                seconds = int(seconds / 2)
            else:
                seconds = 15
            vm = self.find_vm(self.vm_name)
            i = i + 1
            vm_up = vm.guest.guestOperationsReady
        if i == 6:
            print "VM DID NOT START CORRECTLY. Failing Script"
            sys.exit(666)

    def Post_OS_Configuration(self):
        creds = vim.vm.guest.NamePasswordAuthentication(username=self.root_user, password=self.root_pass)
        vm = self.find_vm(self.vm_name)
        print "Connecting to %s to configure.." % self.vm_name
        proc_manager = self.vmware_connection.content.guestOperationsManager.processManager
        print "Creating directories and mounting filesystems"
        proc_manager.StartProgramInGuest(vm=vm, auth=creds, spec=self.create_program_spec("/bin/mkdir", ['-p',
                                                                                                         '/etc/puppetlabs/facter/facts.d/']))
        proc_manager.StartProgramInGuest(vm=vm, auth=creds, spec=self.create_program_spec("/bin/cp", ['-f',
                                                                                                      '/etc/resolv.conf.prod',
                                                                                                      '/etc/resolv.conf']))
        time.sleep(1)
        # run OS Specific commands
        if self.vm_osver == 6:
            print "Running OEL 6 specific commands"
        if self.vm_osver == 5:
            print "Running OEL 5 specific commands"
        print "Creating Puppet Facts"
        # Create facts for puppet
        proc_manager.StartProgramInGuest(vm=vm, auth=creds, spec=self.create_program_spec("/bin/echo", [
            "tmo_cpus=" + str(self.vm_CPUs), '>>', '/etc/puppetlabs/facter/facts.d/build.txt']))
        proc_manager.StartProgramInGuest(vm=vm, auth=creds, spec=self.create_program_spec("/bin/echo", [
            "tmo_memory=" + str(self.vm_memory), '>>', '/etc/puppetlabs/facter/facts.d/build.txt']))
        proc_manager.StartProgramInGuest(vm=vm, auth=creds, spec=self.create_program_spec("/bin/echo", [
            "tmo_diskcount=" + str(self.vm_diskcount), '>>', '/etc/puppetlabs/facter/facts.d/build.txt']))
        proc_manager.StartProgramInGuest(vm=vm, auth=creds, spec=self.create_program_spec("/bin/echo", [
            "oel_version=" + str(self.vm_osver), '>>', '/etc/puppetlabs/facter/facts.d/build.txt']))
        proc_manager.StartProgramInGuest(vm=vm, auth=creds, spec=self.create_program_spec("/bin/echo", [
            "organization=" + self.vm_org, '>>', '/etc/puppetlabs/facter/facts.d/build.txt']))
        proc_manager.StartProgramInGuest(vm=vm, auth=creds, spec=self.create_program_spec("/bin/echo", [
            "organizational_unit=" + self.vm_ou, '>>', '/etc/puppetlabs/facter/facts.d/build.txt']))
        proc_manager.StartProgramInGuest(vm=vm, auth=creds, spec=self.create_program_spec("/bin/echo",
                                                                                          ["pci=" + self.vm_pci, '>>',
                                                                                           '/etc/puppetlabs/facter/facts.d/build.txt']))
        proc_manager.StartProgramInGuest(vm=vm, auth=creds, spec=self.create_program_spec("/bin/echo", [
            "server_type=" + self.vm_type, '>>', '/etc/puppetlabs/facter/facts.d/build.txt']))
        time.sleep(5)
        proc_manager.StartProgramInGuest(vm=vm, auth=creds, spec=self.create_program_spec("/bin/sed", ["-i",
                                                                                                       "'s/production/oel_zebras/'",
                                                                                                       "/etc/puppetlabs/puppet/puppet.conf"]))
        time.sleep(5)
        proc_manager.StartProgramInGuest(vm=vm, auth=creds, spec=self.create_program_spec("/sbin/init", ["6"]))
        print "Successfully ran commands against vm."

    def find_template(self, osver):
        print "Finding appropriate VM template for OEL %s" % osver
        osver = int(self.vm_osver)
        if osver == 6:
            template_vm = self.find_vm(self.oel_6_template_name)
        elif osver == 5:
            template_vm = self.find_vm(self.oel_5_template_name)
        else:
            print "Unable to determine template to use. exiting..."
            sys.exit(3)
        print "Found template %s" % template_vm.name
        return template_vm

    def create_customization_spec(self):
        guest_map = vim.vm.customization.AdapterMapping()
        guest_map.adapter = vim.vm.customization.IPSettings()
        guest_map.adapter.ip = vim.vm.customization.FixedIp()
        guest_map.adapter.ip.ipAddress = self.vm_ip
        guest_map.adapter.subnetMask = "255.255.255.0"
        guest_map.adapter.gateway = self.vm_ip[0:self.vm_ip.rfind(".")] + ".1"
        guest_map.adapter.dnsDomain = self.vm_dns_domain
        nic_settings = [guest_map]  # configspec.nicSettingMap is required to be iterable
        # DNS settings
        globalip = vim.vm.customization.GlobalIPSettings()
        globalip.dnsServerList = self.vm_dns_servers
        globalip.dnsSuffixList = self.vm_dns_suffixs
        # Hostname settings
        ident = vim.vm.customization.LinuxPrep()
        ident.domain = self.vm_dns_domain
        ident.hostName = vim.vm.customization.FixedName()
        ident.hostName.name = self.vm_name

        customspec = vim.vm.customization.Specification()
        customspec.nicSettingMap = nic_settings
        customspec.globalIPSettings = globalip
        customspec.identity = ident
        return customspec

    def create_relocation_spec(self):
        relocate = vim.vm.RelocateSpec()
        relocate.pool = self.find_resource_pool()
        datastorecluster = self.find_datastorecluster()
        relocate.datastore = self.get_datastore(datastorecluster)
        return relocate

    def create_config_spec(self, devices):
        conf_spec = vim.vm.ConfigSpec()
        conf_spec.memoryMB = int(self.vm_memory) * 1024
        conf_spec.numCPUs = int(self.vm_CPUs)
        conf_spec.memoryHotAddEnabled = True
        conf_spec.cpuHotAddEnabled = True
        conf_spec.deviceChange = devices
        return conf_spec

    def create_clone_spec(self, relocate_spec, config_spec, customization_spec):
        # Clone spec
        clonespec = vim.vm.CloneSpec()
        clonespec.location = relocate_spec
        clonespec.config = config_spec
        clonespec.customization = customization_spec
        clonespec.powerOn = True
        clonespec.template = False
        return clonespec

    def get_folder_for_vm(self):
        root_folder = self.find_folder(self.vmware_root_folder)
        root_folder_name = root_folder.name
        application = self.vm_name[3:7].upper()
        print "Looking for folder {application} in {root_folder_name}".format(**locals())
        folder_name = self.find_folder_in_folder(root_folder, application)
        folder = None
        if folder_name == None:
            print "Unable to find folder {application}, creating it in {root_folder_name} and placing VM.".format(**locals())
            folder = root_folder.CreateFolder(application)
        else:
            print "Found existing folder: {application}. Placing VM in folder.".format(**locals())
            folder = folder_name
        return folder

    def __init__(self, dc, cl, nm, cpu, mem, ip, osver, diskcount, org, ou, pci, servertype):
        self.vmware_datacenter = dc
        self.vmware_server = self.get_vmware_server(dc.lower())
        self.vmware_user = "<service account user"
        self.vmware_password = "<service account password>"
        self.vmware_port = 443
        self.vmware_connection = self.connect_to_vmware()
        self.vmware_root_folder = "<placement folder>"
        self.vm_cluster = self.find_cluster(cl.upper())
        self.vm_name = nm.lower()
        self.vm_CPUs = cpu
        self.vm_memory = mem
        self.vm_ip = ip
        self.vm_osver = float(osver)
        self.vm_diskcount = diskcount
        self.vm_org = org.upper()
        self.vm_ou = ou.upper()
        self.vm_pci = pci.upper()
        self.root_user = "user"
        self.root_pass = "pass"
        self.vm_type = servertype.upper()
        self.vm_dns_servers = "10.130.32.52"  # temporary, will get set by puppet later
        self.vm_dns_suffixs = "<dns suffixs>"
        self.vm_dns_domain = "<dns domain>"
        if dc.lower() == 'dc1':
            self.oel_6_template_name = "oel_6_template"
            self.oel_5_template_name = "oel_5_template"
        elif dc.lower() == 'dc2':
            self.oel_6_template_name = "oel_6_template"
            self.oel_5_template_name = "oel_5_template"
        elif dc.lower() == 'dc3':
            print "Why are you building in DC3. We have no templates there!!!"
            exit(666)
        else:
            print "I don't know where you are trying to build these VM's but its the wrong place"
            exit(666)
