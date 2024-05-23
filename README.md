# Intelligent Accelerators Resource Management (IARM) for the AI@EDGE H2020 Project

### Description:
IARM selects each time the most suitable nodes, in a Kubernetes cluster (MEC System),
for the deployment of Artificial Intelligence Functions (AIFs),
leveraging system-level metrics and the accelerators' availability, while meetings specific SLOs, eg., low latency.
It also supports dynamic migration of the AIFs between the accelerators/nodes
of the cluster (within the MEC System) to accommodate for abrupt changes..

---
## IARM's main function ##

IARM receives an AIF Descriptor yaml (AIFD.yml) as a request from MEO, for inference serving.
It then chooses the most suitable AIF version and cluster node for the AIF deployment, and
responds to MEO with a sorted list of the AIF deployment options. The supported versions span from multi-arch CPU (x86, ARM), and multi-framework (TF, TensorRT), to heterogeneous hardware (GPU, FPGA).

**Input:**
- **AIFD.yaml**: YAML file - The AIF Descriptor yaml

**Response:**
- **Selection List**: list of lists: [[<helm-chart>, <node_name>, <aif-name>, {values}], [<helm-chart>, <node_name>, <aif-name>, {values}]] - 
A sorted list containing the AIF deployment options
---

## IARM's endpoint for client ##

IARM also responds to clients' requests to its /api/v3/server_port endpoint,
providing the client with the IP and Port of the most suitable, currently deployed AIF
for the client's requested task.

- **Client's JSON request**: {"APP_ID": "Image Classification"} or {"APP_ID": "Road_SemSeg"}
- **JSON response**: {'SERVER_IP': <AIF's IP>, 'SERVER_PORT': <AIF's port>}
---

IARM's service runs on port 5035.

### Prerequisites:
* #### MEO:
**Default local IP considered**: 192.168.1.228, **Port**: 30445
* #### Redis Time Series Database:
**IP and Port**: Acquired from and ENV file, mounted in /scrape/.env as a HostPath, located on the node IARM is deployed.
* #### Redis Database:
**Default local IP considered**: 192.168.1.228, **Port**: 30002

---
### Deploy IARM:
```
kubectl apply -f iarm_service.yaml
kubectl apply -f iarm_deploy_v2.yaml
```
