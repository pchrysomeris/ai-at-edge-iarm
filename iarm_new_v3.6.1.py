from flask import Flask, request, Response
import json
import yaml
from kubernetes import client, config
import time
import threading
import sys
import requests
import queue
import random

## access Redis info through /scrape/.env: ##
import redis
#r = redis.Redis(host='redis-service-ai-at-edge-worker-01.monitoring', port=6379)
#r = redis.Redis(host='192.168.1.228', port=30001)
import os
# Load the environment variables from the file
from dotenv import load_dotenv
load_dotenv("/scrape/.env")
# Get the values of NODE_NAME and REDIS_IP
redis_ip = os.environ.get("REDIS_IP")
redis_port = os.environ.get("REDIS_PORT")
r = redis.Redis(host=redis_ip, port=redis_port)
##

#flask service
app = Flask(__name__)

#config.load_kube_config(config_file='/home/panos/Desktop/ai-at-edge/.kube/config')
config.load_kube_config(config_file='/home/iccs/.kube/config')
v1 = client.CoreV1Api()


#dictionaries that map AIFD keys to values:
hardwareType_dict = {"GPU": "GPU", "AGX": "GPU", "FPGA": "FPGA", "ALVEO": "FPGA"}
hardwareDevice_dict = {"nvidia.com/gpu": "nvidia.com/gpu", "NVIDIA V100S": "nvidia.com/gpu",
"nvidia.com/gpu-agx": "nvidia.com/gpu-agx", "Jetson AGX Xavier Series": "nvidia.com/gpu-agx",
"xilinx.com/fpga-xilinx_u280": "xilinx.com/fpga-xilinx_u280", "Xilinx Alveo U280": "xilinx.com/fpga-xilinx_u280"}
cpuarchitecture_dict = {"x86": "x86", "amd64": "x86", "ARM": "ARM", "arm64": "ARM"}
#print(hardwareDevice_dict["Jetson AGX Xavier Series"])

## Get the priority index of a tuple in the list
#function "get_priority_index" takes a tuple (a deployment suggestion of the AIF application) as an argument and returns
# an integer that represents its priority index.
def get_priority_index(t):
	#hardware devices in the order of preference for running the AIF application
	priority_list = ["gpu-amd", "alveo-u280", "gpu-agx", "cpu-amd", "cpu-arm"]
	
	# Loop through the priority list and find the matching priority string
	for i, p in enumerate(priority_list):
    		#print(i,p): 0 {p1}   1 {p2}   2 {p3} etc.
    		# if the priority string is a substring of the first item of the tuple:
    		if p in t[0]:
    			#return the index number
        		return i
	# Return a large number if no match is found
	return len(priority_list)

#get the cores utilization of all nodes from redis
def get_node_cores_utilization(node_cores_utilization_dict):
	#System level metrics
	#for key in r.scan_iter("*"):
	for key, value in keys_dict.items():
		#skip application level metrics
		if key.startswith(b'AIF'):
			continue
		#print(key)
		#print(r.ts().get(key))
		# range_reply = r.ts().revrange(key, 0, "+")
		# print(range_reply)
		
		#if key starts with "cpu" and ends with a node_name (from the node_cores_utilization_dict),
		#update the node_cores_utilization_dict values:
		if key.startswith(b'cpu'):
			for node_name, (node_cores_utilization, node_cores) in node_cores_utilization_dict.items():
				#print(node_name, node_cores_utilization, node_cores)
				#if node_name in key:
				if key.endswith('{node}'.format(node=node_name).encode('utf-8')):
					#count the num of cores
					node_cores += 1
				
					#if key value is empty, show 0 cpu utilization
					#if not r.ts().get(key):
					if not value:
						core_utilization = 0
					else:
						#get latest key value, and add them:
						#core_utilization = r.ts().get(key)[1]
						core_utilization = value[1]
				
					#get avg key value (latest to earliest) over 5s, and add them:
					#g = r.ts().revrange(key, 0, "+", aggregation_type='avg', bucket_size_msec=5000)
					#core_utilization = g[0][1]
					#print(core_utilization)
					node_cores_utilization += core_utilization
					
					#update the values of the key "node_name"
					node_cores_utilization_dict[node_name] = (node_cores_utilization, node_cores)
	
	for node, (node_cores_utilization, node_cores) in node_cores_utilization_dict.items():
		#print(node_cores_utilization, node_cores)
		#else 0: if node_cores = 0, then the key didn't exist so just show 0 cpu utilization
		print("node_cores_utilization (%) of node", f'"{node}"',  ":", node_cores_utilization/node_cores if node_cores != 0 else 0)
	
	return node_cores_utilization_dict

#reorder list's items with cpu_string by cpu utilization:
def list_reorder_by_cpu_utilization(original_list, cpu_string):

	# Define a function to sort the tuples (t) by the node's cpu utilization (t[1]) in ascending order
	def sort_by_cpu(t):
    		return node_cpu_utilization_dict.get(t[1], 2)	
	
	# Filter the list to get only the tuples that have the cpu_string
	#cpu_string_list = [item for item in original_list if (cpu_string[0] in item[0]) or (cpu_string[1] in item[0])]
	cpu_string_list = [item for item in original_list if cpu_string in item[0]]
	print("cpu_string_list:", cpu_string_list)
	#if no item matches the cpu_string (empty list), return original list
	if not cpu_string_list:
		print("selection list does not contain any CPU version AIF")
		return original_list
	
	#list of the cpu nodes
	cpu_node_list = [item[1] for item in cpu_string_list]
	print("cpu_node_list:", cpu_node_list)
	
	#initial values of every node in cpu_string_list
	node_cores_utilization_dict = {item[1]: (0, 0) for item in cpu_string_list}
	#print("node_cores_utilization_dict:", node_cores_utilization_dict)
	
	#update node_cores_utilization_dict values from redis
	node_cores_utilization_dict = get_node_cores_utilization(node_cores_utilization_dict)
	#node_cores_utilization_dict = {'iccs-worker2': (random.randint(0, 10), 3), 'iccs-worker1': (random.randint(0, 10), 3), 'zynqmp': (random.randint(0, 10), 3)}
	print("node_cores_utilization_dict:", node_cores_utilization_dict)
	
	#from node_cores_utilization_dict (values: (node_cores_utilization, node_cores)), get the cpu utilization of each node:
	node_cpu_utilization_dict = {}
	for key, value in node_cores_utilization_dict.items():
		node_cpu_utilization_dict[key] = value[0]/value[1] if value[1] != 0 else 0
	print("node_cpu_utilization:", node_cpu_utilization_dict)
	
	# Sort the cpu_string_list of tuples by the node_cpu_utilization_dict
	cpu_string_list.sort(key=sort_by_cpu)
	
	print("sorted cpu_string_list by node_cpu_utilization:", cpu_string_list)
	
	# Create a new list to store the final result
	sorted_list = []

	# Loop through the original list and append the items to the final list
	for item in original_list:
		# If the item has cpu_string, pop the first item from the cpu_string_list and append it to the sorted list
		#if (cpu_string[0] in item[0]) or (cpu_string[1] in item[0]):
		if cpu_string in item[0]:
			sorted_list.append(cpu_string_list.pop(0))
		# Otherwise, just append the item as it is from the original list
		else:
			sorted_list.append(item)
			
	# Return the final list
	#print("sorted_list:", sorted_list)
	return sorted_list


def check_node_availability(version, node, gpu_arch, deployment_info):
	print("******* NEW NODE *******")
	#exclude master node from pool of available nodes for scheduling
	if "node-role.kubernetes.io/master" in node.metadata.labels:
		print(node.metadata.name, ": is a master node.")
		return deployment_info
	#ignore nodes that are tainted
	if not node.spec.taints == None:
		print(node.metadata.name, ": is tainted")
		return deployment_info

	print(node.metadata.name)
	#if AIF supports acceleration (hw type is not "CPU"):
	if "accelerationDescriptor" in version["requirements"].keys():
		#check allocatable resources of the node for the required hw device of the AIF version:
		#matching full resource name in the cluster (to the AIF hw device), else empty list if no match found in the node
		matching = [s for s in node.status.allocatable if hardwareDevice_dict[version['requirements']['accelerationDescriptor']['hardwareDevice']] in s]
		#if AIF's GPU version has different architecture from the node, ignore node
		if hardwareType_dict[version['requirements']['accelerationDescriptor']['hardwareType']] == "GPU" and gpu_arch != node.status.node_info.architecture:
			return deployment_info
			
		#if matching list is not empty (match found), check if required resource is available:
		if matching:
			#number of allocatable resources of the matching full resource name in the node
			allocatable_resources = int(node.status.allocatable[matching[0]])
			print("node", f'"{node.metadata.name}"', "has", allocatable_resources, "allocatable", f'"{matching[0]}"', "resources")
			
			#number of AVAILABLE resources of the matching full resource name in the node
			available_resources = allocatable_resources
			
			#check all running pods 
			#for pod in v1.list_pod_for_all_namespaces(field_selector='status.phase==Running').items:
			#check all pods
			#for pod in v1.list_pod_for_all_namespaces().items:
			for pod in pods:
				#if pod is running in the node being examined
				if pod.spec.node_name == node.metadata.name:
					#check all containers of the pod
					for container in pod.spec.containers:
						#skip container if it has no resource request
						if not container.resources.requests:
							continue
						else:
							#container has resources requests: 
							#if matching full resource name in the node is the same as the resources requests:
							if matching[0] in container.resources.requests:
								#number of requested resources of the matching full resource name in the node
								requested_resources = int(container.resources.requests[matching[0]])
								print("container", f'"{container.name}"', "of pod", f'"{pod.metadata.name}"', "has", requested_resources, f'"{matching[0]}"', "resources requests in node", f'"{node.metadata.name}"')
								
								available_resources = available_resources - requested_resources
			print("number of available", f'"{matching[0]}"', "resources in node " + f'"{node.metadata.name}"' + ":", available_resources)				
			#if there are available resources of the matching full resource name in the node:
			if available_resources > 0:
				#first available resource match found!
				print("match found!")
				print("matching resource:", matching[0], "in node:", node.metadata.name)
				#return [(selected AIF version's helm-chart, selected cluster node name (that has the required resources),
				# {helm-chart values})]
				deployment_info.append((version['helm-chart'], node.metadata.name, {'test_value': 2}))
				print("selection list thus far: ", deployment_info)
				return deployment_info
			
	else:
		#if AIF supports CPU only (hw type is "CPU"), check architecture:
		#if architecture is x86 (or amd64):
		if cpuarchitecture_dict[version['requirements']['virtualComputeDescriptor']['virtualCpu']['cpuarchitecture']] == 'x86':
			#and node arch matches:
			if node.status.node_info.architecture == 'amd64':
				#first available resource match found!
				print("match found!")
				print("matching resource: ", "CPU -", node.status.node_info.architecture, "in node: ", node.metadata.name)
				#return [(selected AIF version's helm-chart, selected cluster node name (that has the required resources),
				# {helm-chart values})]
				deployment_info.append((version['helm-chart'], node.metadata.name, {'test_value': 2}))
				print("selection list thus far: ", deployment_info)
				return deployment_info
		#if architecture is ARM (or arm64):
		elif cpuarchitecture_dict[version['requirements']['virtualComputeDescriptor']['virtualCpu']['cpuarchitecture']] == 'ARM':
			#and node arch matches:
			if node.status.node_info.architecture == 'arm64':
				#first available resource match found!
				print("match found!")
				print("matching resource: ", "CPU -", node.status.node_info.architecture, "in node: ", node.metadata.name)
				#return [(selected AIF version's helm-chart, selected cluster node name (that has the required resources),
				# {helm-chart values})]
				deployment_info.append((version['helm-chart'], node.metadata.name, {'test_value': 2}))
				print("selection list thus far: ", deployment_info)
				return deployment_info
	
	return deployment_info	

#search cluster nodes for available resources for the AIF
def version_deployment(sorted_versions_list, deployment_info):
	print("Looking for an available cluster node for the AIF:") 
	#for each of the sorted versions of the AIF:
	for version in sorted_versions_list:
		print("********************* NEW VERSION ********************************")
		print("version name: ", version['name'])
		#store current deployment_info length for comparison
		l = len(deployment_info)
		#if AIF supports acceleration:
		if "accelerationDescriptor" in version["requirements"].keys():
			print("hw type: " + version['requirements']['accelerationDescriptor']['hardwareType'] + ", hw device: " + version['requirements']				['accelerationDescriptor']['hardwareDevice'])
			#label agx with arm64 architecture (to differentiate nvidia.com/gpu from nvidia.com/gpu-agx
			# in the matching (AIF hw device, node resource) process)
			if "agx" in hardwareDevice_dict[version['requirements']['accelerationDescriptor']['hardwareDevice']]:
				gpu_arch = "arm64"
			else:
				gpu_arch = "amd64"
		else:
			#AIF supports CPU only
			gpu_arch = ""
			print("hw type: " + "CPU" + ", architecture: " + version['requirements']['virtualComputeDescriptor']['virtualCpu']['cpuarchitecture'])
		#check allocatable resources of each cluster node:
		#for node in v1.list_node().items:
			#print(node.status.allocatable)
			#print(node.status.node_info.architecture)

		#check all the cluster nodes for resource availability:
		#for node in v1.list_node().items:
		for node in nodes:
			#for each node, update the deployment_info list suitably 
			deployment_info = check_node_availability(version, node, gpu_arch, deployment_info)
			
		#if available resource match for the current AIF version hasn't been found in the cluster nodes:
		if not (len(deployment_info) > l):
			print(version['name'], "has not found an available resource in the cluster nodes")
	#if there is no available resource match in the cluster nodes for all the versions of this AIF:
	if not deployment_info:
		print("No version of this **aifd** has a matching available resource in the cluster nodes")
	
	return deployment_info

#indefinite loop for the daemon thread u
def api_and_redis_wrapper(v1, r, event):
	while True:
		#"global" so that the update of "nodes" and "pods" lists and Redis dict can be seen from IARM
		global nodes, pods
		nodes, pods = v1_kubeapi_list_update(v1, nodes, pods)
		
		global keys_dict
		keys_dict = redis_dict_update(r)
		
		# Set the event when done
		event.set()
		print("local IARM lists and Redis dict update!")
		time.sleep(10)

#update the local "nodes" and "pods" lists of IARM from Kubernetes API
def v1_kubeapi_list_update(v1, nodes, pods):
	nodes = []
	pods = []
	for node in v1.list_node().items:
		nodes.append(node)
	for pod in v1.list_pod_for_all_namespaces().items:
		pods.append(pod)
	return nodes, pods

#update the local "keys:values" Redis dict of IARM from redis
def redis_dict_update(r):
	keys_dict = {}
	for key in r.scan_iter("*"):
		#get latest key's value (tuple)
		keys_dict[key] = r.ts().get(key)
	return keys_dict


#upload the upcoming AIF deployment's name, and its aifd, to redis
def redis_set(r_kv, aif_name, aifd):
	#create redis key and value:
	key = aif_name
	value = aifd
	#SET
	json_value = json.dumps(value)
	r_kv.set(key, json_value)
	print(key, "was uploaded to redis-kv")


#check for available AIF version improvement
def version_improvement(r_kv):
	#get all deployed AIFs from MEO (".json()" will parse the response content as JSON and return a Python dictionary):
	get_aif_response = requests.get('http://192.168.1.228:30445/meo/aifd/app').json()
	#whether AIF migration from CPU to a better CPU is allowed
	CPU_migration = False

	#for each deployed AIF (in key-value redis): run the iarm_update() and get the updated suggested sorted_deployment_info for that AIFD
	for key in r_kv.scan_iter("*"):
		#get the key's value ("aifd")
		unpacked_value = json.loads(r_kv.get(key).decode('utf-8'))
		
		#temporarily redirect sys.stdout to a temp file (for the duration of the iarm_update()), so as not to congest the console output
		stdout = sys.stdout
		with open('file', 'w') as sys.stdout:
			sorted_deployment_info = iarm_update(unpacked_value)
		sys.stdout = stdout
		
		#print("improved:", sorted_deployment_info)
		
		###check if key "aif_name" (from redis-kv) is in the MEO-deployed AIFs dict
		matching = None
		#for every item in MEO's dict:
		for item in get_aif_response:
			#if aif_name is found:
			if key.decode('utf-8') in item['name']:
				#save the item and break the loop
				matching = item
				break
		#if aif_name has been found
		if matching:
			#save the AIF's currently deployed helm_chart and node_name in a tuple
			current_position = (matching['bodytosend']['repochart_name'], matching['bodytosend']['values']['nodeSelector']['kubernetes.io/hostname'], {'test_value': 2})
			print(key.decode('utf-8') + "'s current_position:", current_position)
			
			#check if current_position tuple is in sorted_deployment_info
			if current_position in sorted_deployment_info:
				#get the current_position's index in the sorted_deployment_info
				selection_list_index = sorted_deployment_info.index(current_position)
				
				#if current position is the first tuple in sorted_deployment_info
				if selection_list_index == 0:
					print(key.decode('utf-8'), "is currently at its best performance in the cluster")
				elif CPU_migration is False:
					if not "cpu" in sorted_deployment_info[0][0]:
						#migrate AIF to a better position
						print("improved:", sorted_deployment_info)
						migrate(r_kv, unpacked_value, matching['bodytosend']['release_name'], sorted_deployment_info[0][1], sorted_deployment_info[0][0])
				
				else:
					#migrate AIF to a better position
					print("improved:", sorted_deployment_info)
					migrate(r_kv, unpacked_value, matching['bodytosend']['release_name'], sorted_deployment_info[0][1], sorted_deployment_info[0][0])
			else:
				#if sorted_deployment_info's selections do not include the AIF's current position:
				#get the priority list's index of current_position tuple
				priority_index = get_priority_index(current_position)
				#print(priority_index)
			
				#if current position is the highest in priority list
				if priority_index == 0:
					print(key.decode('utf-8'), "is currently at its - absolute - best performance in the cluster")		
				else:
					#if the first tuple in sorted_deployment_info has higher priority than AIF's current position
					if get_priority_index(sorted_deployment_info[0]) < priority_index:
						#migrate AIF to a better position
						print("improved:", sorted_deployment_info)
						migrate(r_kv, unpacked_value, matching['bodytosend']['release_name'], sorted_deployment_info[0][1], sorted_deployment_info[0][0])
					#if they have equal priorities
					elif get_priority_index(sorted_deployment_info[0]) == priority_index:
						if CPU_migration is True:
							if "cpu" in current_position[0]:
								#migrate CPU version AIF to a better CPU position
								print("improved:", sorted_deployment_info)
								migrate(r_kv, unpacked_value, matching['bodytosend']['release_name'], sorted_deployment_info[0][1], sorted_deployment_info[0][0])
					else:
						#current position is not the highest in the priority list, but it is higher than the currently available ones in sorted_deployment_info
						print(key.decode('utf-8'), "is currently at its best performance in the cluster")
					

#migrate aif's current version to a new version
def migrate(r_kv, aifd, aif_current_name, destination_node, new_helm_chart):
	#MIGRATION INFO
	
	#AIF's new name:
	# Split the AIF's current name by the "-" delimiter
	aif_current_name_list = aif_current_name.split("-")
	# Join the first two elements of the AIF's current_name_list with the "-" delimiter
	aif_new_name = "-".join(aif_current_name_list[:2])
	#add unique identifier to the AIF's new name
	aif_new_name = aif_new_name + "-" + str(round(time.time()))
	
	#AIF's new node port:
	#keep generating new_port until it is not already assigned to a different service in the cluster
	node_port_available = False
	while not node_port_available:
		#valid node ports
		new_node_port = random.randint(30000, 32767)
		node_port_available = True
		#check all services if port is taken
		for service in v1.list_service_for_all_namespaces().items:
			if new_node_port == service.spec.ports[0].node_port:
				node_port_available = False
	 
	# Create a dictionary for the request body
	data = {
	  "aif_name": aif_current_name,
	  "destination_node": destination_node,
	  "helm_chart": new_helm_chart,
	  "new_name": aif_new_name,
	  "new_service_port": str(new_node_port)
	}
	
	#print(data)
	# Convert the dictionary to a JSON string
	data = json.dumps(data)

	# Create a dictionary for the request headers
	headers = {
	  "accept": "application/json",
	  "Content-Type": "application/json"
	}
	
	#print(headers)
	# Send a PUT request to MEO
	response = requests.put("http://192.168.1.228:30445/meo/aif/migrate/", data=data, headers=headers)

	# Print the response status code and content
	print(response.status_code)
	print(response.content)
	print("AIF migration completed!")
	print(aif_current_name, "migrated to", f'"{aif_new_name}"', "at", destination_node, "with new helm chart:", new_helm_chart, "and new node port:", new_node_port)
	
	#upload the migrated AIF's new name, and its aifd, to a key-value redis
	redis_set(r_kv, aif_new_name, aifd)
	#delete previous AIF's version from the key-value redis:
	r_kv.delete(aif_current_name)
	
					
#indefinite loop for the daemon thread t: it runs "version_improvement()" everytime the event is set (by the api_and_redis_wrapper()),
#meaning everytime the local lists and dict of IARM are updated
def wrapper(r_kv, event):
	while True:
		#waiting for the event to be set
		event.wait()
		version_improvement(r_kv)
		# unset the event
		event.clear()

#delete all keys from key-value redis
def delete_keys(r_kv):
	for key in r_kv.scan_iter("*"):
		r_kv.delete(key)

def iarm_update(aifd):
	#check available versions for this AIF
	versions_list = []
	acceleration_versions_list = []
	cpu_versions_list = []
	i = 0
	#kdu: list of versions of the application
	while i < len(aifd["kdu"]):
		#if the AIFD has an "accelerationDescriptor" field in the "kdu" in the yaml:
		if "accelerationDescriptor" in aifd["kdu"][i]["requirements"].keys():
			acceleration_versions_list.append(aifd["kdu"][i])
		else:
			cpu_versions_list.append(aifd["kdu"][i])
		#all AIF versions
		versions_list.append(aifd["kdu"][i])
		i += 1
	#versions_list contains dictionaries of different versions of the AIF application
	
	#iarm output list of tuples in order of deployment preference: [(helm-chart, node_name, {values}), (helm-chart, node_name, {values})]
	deployment_info = []
	#deployment_info = version_deployment(sorted_versions_list, deployment_info)
	deployment_info = version_deployment(versions_list, deployment_info)
	
	####
	#reorder deployment_info's cpu nodes by their current cpu utilization 
	deployment_info = list_reorder_by_cpu_utilization(deployment_info, "cpu")
	#The sorted_deployment_info list has the tuples ordered by the priority list:
	sorted_deployment_info = sorted(deployment_info, key=get_priority_index)
	return sorted_deployment_info

@app.route("/api/v3/placement", methods=['GET', 'POST'])
def iarm_function():
	##IARM TIME MEASUREMENT
	#IARM start
	t1 = time.time()
	print(t1)
	
	#JSON request: aifd (AIF Descriptor)
	print("JSON request:", request.is_json)
	aifd = request.get_json()
	print("aifd:", aifd)
	#check available versions for this AIF
	print("AIF name: " + aifd["appName"])

	versions_list = []
	acceleration_versions_list = []
	cpu_versions_list = []
	i = 0
	#kdu: list of versions of the application
	#if versions_list (under the "kdu" key in the AIFD yaml) is empty, this AIF is not managed by IARM:
	if not aifd["kdu"]:
		print(aifd["appName"], ": is not an AI acceleration function")
		print("Exiting...")
		exit(0)
	while i < len(aifd["kdu"]):
		#if the AIFD has an "accelerationDescriptor" field in the "kdu" in the yaml:
		if "accelerationDescriptor" in aifd["kdu"][i]["requirements"].keys():
			acceleration_versions_list.append(aifd["kdu"][i])
		else:
			cpu_versions_list.append(aifd["kdu"][i])
		#all AIF versions
		versions_list.append(aifd["kdu"][i])
		i += 1
	#versions_list contains dictionaries of different versions of the AIF application
	print("number of available AIF versions: " + str(len(versions_list)))
	print("versions list: ", versions_list)

	#sorted versions list of the AIF:
	#sorted_versions_list = sort_versions(versions_list)
	#print("sorted versions list: ", sorted_versions_list)


	#iarm output list of tuples in order of deployment preference: [(helm-chart, node_name, {values}), (helm-chart, node_name, {values})]
	deployment_info = []
	#deployment_info = version_deployment(sorted_versions_list, deployment_info)
	deployment_info = version_deployment(versions_list, deployment_info)
	
	####
	#reorder deployment_info's cpu nodes by their current cpu utilization 
	deployment_info = list_reorder_by_cpu_utilization(deployment_info, "cpu")
	
	###
	#The sorted_deployment_info list has the tuples ordered by the priority list:
	#The sorted method takes a key argument that specifies a function to be used for sorting. The code passes the
	#"get_priority_index" function as the key argument, which means that the sorted method will automatically apply this
	#function to each element/tuple of the deployment_info list and sort them according to the returned values.
	##
	#If there are multiple tuples with the same priority, they are sorted by their original order in the list. 
	#(thus "cpu" tuples are keeping their prior reordering by cpu utilization)
	sorted_deployment_info = sorted(deployment_info, key=get_priority_index)
	###
	
	## AIF NAME ##
	#add unique "aif_name" (unique identifier of the upcoming AIF deployment) to the selection list's tuples:
	app_name = aifd["appName"].lower()
	if "segmentation" in app_name:
		aif_name = "aif-semseg"
	elif "classification" in app_name:
		aif_name = "aif-class"
	else:
		aif_name = "aif"
	
	aif_name = aif_name + "-" + str(round(time.time()))
	
	#This code creates a new list by iterating over each tuple in the original list and slicing it into two parts: the first two elements and the rest.
	#Then, it concatenates the first part, the item “aif_name” as a singleton tuple, and the second part using the + operator.
	#This results in a new tuple with “aif_name” inserted at the third position.
	sorted_deployment_info = [tup[:2] + (aif_name,) + tup[2:] for tup in sorted_deployment_info]
	##
	
	#print("selection list: ", deployment_info)
	print("selection list: ", sorted_deployment_info)
	
	
	#if sorted_deployment_info is not empty:
	if sorted_deployment_info:
		#upload the upcoming AIF deployment's name, and its aifd, to a key-value redis
		#format of each key-value entry: aif_name:aifd
		redis_set(r_kv, aif_name, aifd)
	
	deployment_info_json = [{"helm-chart":"aiatedge/sentiment-analysis-chart", "node_name":"ai-at-edge-worker-01", "values": {
            "nodeSelector": {"kubernetes.io/hostname": "ai-at-edge-worker-01"},
            "useCustomContent": "Yes",
            "websiteData": {
                "index.html": "goodbye!"
            }}}]
            
	deployment_info_json_2 = [["aiatedge/sentiment-analysis-chart", "ai-at-edge-worker-01", {"values": {
            "nodeSelector": {"kubernetes.io/hostname": "ai-at-edge-worker-01"},
            "useCustomContent": "Yes",
            "websiteData": {
                "index.html": "goodbye!"
            }}}]]

	##IARM TIME MEASUREMENT
	#IARM end
	t2 = time.time()
	print(t2)
	print("IARM time duration:", t2-t1)
	
	#JSON response: list of lists: [[helm-chart, node_name, aif-name, {values}], [helm-chart, node_name, aif-name, {values}]]
	return Response(response=json.dumps(sorted_deployment_info),status=200,mimetype='application.json')


#get the AIF port (and AIF node's IP) of the inference_task-matching AIF in the cluster
def get_AIF_port(v1, aif_inference_task):
	#get all deployed AIFs from MEO (".json()" will parse the response content as JSON and return a Python dictionary):
	get_aif_response = requests.get('http://192.168.1.228:30445/meo/aifd/app').json()
	
	if aif_inference_task == "Image Classification":
		aif_substring = "aif-class"
	elif aif_inference_task == "Road_SemSeg":
		aif_substring = "aif-semseg"
	else:
		#if inference_task is not "classification" or "segmentation", put 0 as AIF port/IP and return
		q.put([0, 0])
		return
		
	#check if "aif_substring" (from client's request) is in the MEO-deployed AIFs dict
	matching_list = []
	#for every item in MEO's dict:
	for item in get_aif_response:
		#if aif_substring is found:
		if aif_substring in item['name']:
			#save the item's [helm-chart, name] to the matching list
			matching_list.append([item['bodytosend']['repochart_name'], item["name"]])
	#if at least one aif_substring has been found
	if matching_list:
		#sort matches according to the priority list
		matching_list_sorted = sorted(matching_list, key=get_priority_index)
		#check all matches of the sorted matching list
		for match in matching_list_sorted:
			aif_name = match[1]
			print("aif_name:", aif_name)
		
			#check all services that match the aif_name to get the AIF's port
			for service in v1.list_service_for_all_namespaces().items:
				#print(service.metadata.name)
				if aif_name in service.metadata.name:
					aif_port = service.spec.ports[0].port
					print("aif_port:", aif_port)
					
					#get AIF's node's IP:
					aif_ip = 0
					for pod in pods:
						if aif_name in pod.metadata.name:
							aif_ip = pod.status.host_ip
							print("aif_ip:", aif_ip)
							break
					
					#put AIF port (and AIF node's IP) in the queue and return (so the highest priority matching AIF's port/IP is returned)
					q.put([aif_port, aif_ip])
					return
		#default aif_port and aif_ip value (if corresponding service is not found in the cluster)
		aif_port = 0
		aif_ip = 0
	else:
		#if aif_substring is not found in the MEO-deployed AIFs dict
		aif_port = 0
		aif_ip = 0
		
	#put AIF port/IP in the queue
	q.put([aif_port, aif_ip])

#get the AIF_inference_task from client's request and return the port (and node IP) of the AIF server performing that inference task in the cluster.
#The "get_AIF_port()" function is run by the separate thread "c".	
@app.route("/api/v3/server_port", methods=['GET', 'POST'])
def response_to_client():
	#client's JSON request: {"APP_ID": "Image Classification"} or {"APP_ID": "Road_SemSeg"}
	client_request = request.get_json()
	aif_inference_task = client_request["APP_ID"]
	
	# create a new thread and start it
	c = threading.Thread(target=get_AIF_port, args=[v1, aif_inference_task])
	c.start()
	print("\"AIF server's port discovery\" IARM thread has started!")
	
	# get the AIF port/IP from the queue (this will block until the result is available)
	queue_response = q.get()
	aif_port = queue_response[0]
	aif_ip = queue_response[1]
	
	#JSON response: {'SERVER_IP': AIF's IP, 'SERVER_PORT': AIF's port}
	aif_response = {'SERVER_IP': aif_ip, 'SERVER_PORT': aif_port}
	return Response(response=json.dumps(aif_response),status=200,mimetype='application.json')

if __name__ == "__main__":
	#iarm python file executed as script
	
	#local kubernetes cluster info
	nodes = []
	pods = []
	#local keys:values Redis dictionary from redis 
	keys_dict = {}
	# Define an event object
	event = threading.Event()
	
	#u = new daemon thread that executes the functions "v1_kubeapi_lists_update()" and "redis_dict_update()" in a loop (api_and_redis_wrapper).
	u = threading.Thread(target=api_and_redis_wrapper, args=[v1, r, event])
	u.daemon = True
	u.start()
	print("daemon \"v1 Kubernetes API lists and Redis dict update\" IARM thread has started!")
	
	# Wait for the event to be set
	#IARM waits for the local "nodes" and "pods" lists, and for the local Redis dict, of IARM to be updated for the first time from Kubernetes API
	# or Redis respectively, before it begins the flask service and the "version improvement" daemon thread
	event.wait()
	print("Local \"Nodes\" and \"Pods\" IARM lists and local Redis dict are updated!")
	
	
	#key-value redis for storing AIF deployments
	r_kv = redis.Redis(host='192.168.1.228', port=30002)
	
	#delete key-value redis
	delete_keys(r_kv)
	print("Key-value redis cleared!")
	
	#t = new daemon thread that executes function "version_improvement()" in a loop (wrapper). 
	#(Daemon thread = background thread that ends when main thread ends)
	t = threading.Thread(target=wrapper, args=[r_kv, event])
	t.daemon = True
	t.start()
	print("daemon \"version improvement\" IARM thread has started!")
	
	# create a global queue object for the response to the client requesting the AIF port, so that thread "c" can pass the AIF port to "response_to_client()" function
	q = queue.Queue()
	
	
	app.run(host="0.0.0.0", port=5035)



