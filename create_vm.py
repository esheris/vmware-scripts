import sys
from vm_builds import VmBuilds

vmware_datacenter = sys.argv[1].lower()
vm_cluster = sys.argv[2].upper()
vm_name = sys.argv[3].lower()
vm_CPUs = sys.argv[4]
vm_memory = sys.argv[5]
vm_ip = sys.argv[6]
vm_osver = sys.argv[7]
vm_diskcount = sys.argv[8]
vm_org = sys.argv[9].upper()
vm_ou = sys.argv[10].upper()
vm_pci = sys.argv[11].upper()
vm_type = sys.argv[12].upper()


vm = VmBuilds(vmware_datacenter, vm_cluster, vm_name, vm_CPUs, vm_memory, vm_ip, vm_osver,vm_diskcount, vm_org, vm_ou, vm_pci, vm_type)
template_vm = vm.find_template(vm.vm_osver)
devices = [vm.create_nic_spec(template_vm), vm.create_scsi_ctrl(int(vm.vm_osver))]
#note, this is an extend not an append!!
devices.extend(vm.create_disks())
reloc_spec = vm.create_relocation_spec()
conf_spec = vm.create_config_spec(devices)
custom_spec = vm.create_customization_spec()
clone_spec = vm.create_clone_spec(reloc_spec, conf_spec, custom_spec)
folder = vm.get_folder_for_vm()
create_task = template_vm.Clone(folder=folder, name=vm.vm_name, spec=clone_spec)
result = vm.WaitTask(create_task, 'Create VM %s' % vm.vm_name)
vm.Wait_For_Vm_To_Boot()
vm.Post_OS_Configuration()
