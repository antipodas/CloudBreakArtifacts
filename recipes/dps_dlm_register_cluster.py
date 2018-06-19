#!/usr/bin/python

import requests, json, socket, time, sys, subprocess
from requests.auth import HTTPBasicAuth

if (len(sys.argv) < 3) or (len(sys.argv) == 4):
  print 'Need at least 2 argument [is_shared_services, dps_host_name] and at most 4 arguments [target_cluster_name, target_dataset_name]'
  exit(1)

dps_admin_user = 'admin'
dps_admin_password = 'admin'
ambari_admin_user = 'admin'
ambari_admin_password = 'admin-password'
ranger_admin_user = 'admin'
ranger_admin_password = 'admin-password'

dps_url = 'https://' + sys.argv[2]
dps_auth_uri = '/auth/in'
dps_lakes_uri = '/api/lakes'
dlm_clusters_uri = '/dlm/api/clusters'
dlm_pair_uri = '/dlm/api/pair'
dlm_pair_uri = '/dlm/api/pair'
ambari_clusters_uri = '/api/v1/clusters'
ranger_service_uri = '/service/public/v2/api/service'
ranger_policy_uri = '/service/public/v2/api/policy'
ranger_hive_allpolicy_search_string = 'all%20-%20database,%20table,%20column'

ranger_port = '6080'
ambari_port = '8080'
namenode_port = '8020'

host_name = socket.getfqdn()
host_ip = socket.gethostbyname(socket.gethostname())
ranger_url = 'http://'+host_name+':'+ranger_port
headers={'content-type':'application/json'}

ambari_cluster_name = json.loads(requests.get('http://'+host_name+':'+ambari_port+ambari_clusters_uri, auth=HTTPBasicAuth(ambari_admin_user, ambari_admin_password)).content)['items'][0]['Clusters']['cluster_name']
ranger_hive_service_name = ambari_cluster_name + '_hive'
ranger_hdfs_service_name = ambari_cluster_name + '_hadoop'

payload = '{"name":"'+ranger_hive_service_name+'","description":"","isEnabled":true,"tagService":"","configs":{"username":"hive","password":"hive","jdbc.driverClassName":"org.apache.hive.jdbc.HiveDriver","jdbc.url":"jdbc:hive2://'+host_name+':2181/;serviceDiscoveryMode=zooKeeper;zooKeeperNamespace=hiveserver2","commonNameForCertificate":""},"type":"hive"}'

ranger_update_result = requests.post(url=ranger_url+ranger_service_uri, auth=HTTPBasicAuth(ranger_admin_user, ranger_admin_password), data=payload, headers=headers, verify=False)
print ranger_update_result
if ranger_update_result.status_code == 400:
  print json.loads(ranger_update_result.content)['msgDesc']
else:
  ranger_hive_service = json.loads(ranger_update_result.content)
  print 'Create Ranger Hive Service: ' + payload
  ranger_hive_service_id = str(ranger_hive_service['id'])
  target_policy = json.loads(requests.get(url=ranger_url+ranger_service_uri+'/'+ranger_hive_service_name+'/policy?policyName='+ranger_hive_allpolicy_search_string, auth=HTTPBasicAuth(ranger_admin_user, ranger_admin_password), data=payload, headers=headers, verify=False).content)[0]
  target_policy['policyItems'][0]['users'].append('beacon')
  target_policy_id = str( target_policy['id'])
  payload = json.dumps(target_policy)
  print 'Add Grant All on Hive Objects to Beacon user : ' + payload
  print 'Result: ' + requests.put(url=ranger_url+ranger_policy_uri+'/'+target_policy_id, auth=HTTPBasicAuth(ranger_admin_user, ranger_admin_password), data=payload, headers=headers, verify=False).content
  
payload = '{"name":"'+ranger_hdfs_service_name+'","description":"","isEnabled":true,"tagService":"","configs":{"username":"hdfs","password":"hdfs","fs.default.name":"hdfs://'+host_name+':'+namenode_port+'","hadoop.security.authorization":true,"hadoop.security.authentication":"simple","hadoop.security.auth_to_local":"","dfs.datanode.kerberos.principal":"","dfs.namenode.kerberos.principal":"","dfs.secondary.namenode.kerberos.principal":"","hadoop.rpc.protection":"authentication","commonNameForCertificate":""},"type":"hdfs"}'

ranger_update_result = requests.post(url=ranger_url+ranger_service_uri, auth=HTTPBasicAuth(ranger_admin_user, ranger_admin_password), data=payload, headers=headers, verify=False)
print ranger_update_result
if ranger_update_result.status_code == 400:
  print json.loads(ranger_update_result.content)['msgDesc']
else:
  ranger_hdfs_service = json.loads(ranger_update_result.content)
  print 'Create Ranger HDFS Service: ' + payload
  payload = '{"policyType":"0","name":"dpprofiler-audit-read","isEnabled":true,"isAuditEnabled":true,"description":"","resources":{"path":{"values":["/ranger/audit","dpprofiler_default"],"isRecursive":true}},"policyItems":[{"users":["dpprofiler"],"accesses":[{"type":"read","isAllowed":true},{"type":"execute","isAllowed":true}]}],"denyPolicyItems":[],"allowExceptions":[],"denyExceptions":[],"service":"'+ranger_hdfs_service_name+'"}'
  print 'Create dpprofiler-audit-read policy: ' + payload
  print 'Result: ' + requests.post(url=ranger_url+ranger_policy_uri, auth=HTTPBasicAuth(ranger_admin_user, ranger_admin_password), data=payload, headers=headers, verify=False).content

print 'Waiting for Ranger Policy to take effect...'
time.sleep(31)

#token = json.loads(requests.post(url = dps_url+dps_auth_uri, data = '{"username":"'+dps_admin_user+'","password":"'+dps_admin_password+'"}', headers=headers, verify=False).text)['token']
token = requests.post(url = dps_url+dps_auth_uri, data = '{"username":"'+dps_admin_user+'","password":"'+dps_admin_password+'"}', headers=headers, verify=False).cookies.pop('dp_jwt')
cookie = {'dp_jwt':token}

requests.get(url = dps_url+'/api/knox/status', cookies = cookie, verify=False).content

tags = ''
if sys.argv[1] == 'true':
  tags = '{"name": "shared-services"}'

payload = '{"allowUntrusted":true,"behindGateway":false,"dcName": "DC02","ambariUrl": "http://'+host_name+':'+ambari_port+'","description":" ","location": 7064,"isDatalake": true,"name": "'+ambari_cluster_name+'","state": "TO_SYNC","ambariIpAddress": "http://'+host_ip+':'+ambari_port+'","properties": {"tags": ['+tags+']}}'
print 'Registering Cluster with Dataplane: ' + dps_url+dps_lakes_uri
print 'Payload: ' + payload
print 'Result: ' + requests.post(url=dps_url+dps_lakes_uri, cookies=cookie, data=payload, headers=headers, verify=False).content

print 'Waiting for DPS registration to take effect...'
time.sleep(3)

if len(sys.argv) > 4:
  target_cluster_name = sys.argv[3]
  target_dataset_name = sys.argv[4]
  dlm_clusters = json.loads(requests.get(url=dps_url+dlm_clusters_uri, cookies=cookie, data=payload, headers=headers, verify=False).content)

  for dlm_cluster in dlm_clusters['clusters']:
    if dlm_cluster['name'] == ambari_cluster_name:
      dlm_dest_cluster_id = str(dlm_cluster['id'])
      dlm_dest_cluster_name = str(dlm_cluster['name'])
      dlm_dest_cluster_beacon = dlm_cluster['beaconUrl']
      dlm_dest_cluster_dc = dlm_cluster['dataCenter']
    elif dlm_cluster['name'] == target_cluster_name:
      dlm_source_cluster_id = str(dlm_cluster['id'])
      dlm_source_cluster_name = str(dlm_cluster['name'])
      dlm_source_cluster_beacon = dlm_cluster['beaconUrl']
      dlm_source_cluster_dc = dlm_cluster['dataCenter']

  payload = '[{"clusterId": '+dlm_source_cluster_id+',"beaconUrl": "'+dlm_source_cluster_beacon+'"},{"clusterId": '+dlm_dest_cluster_id+',"beaconUrl": "'+dlm_dest_cluster_beacon+'"}]'
  print 'Pairing Cluster with Shared Services: ' + dps_url+dlm_pair_uri
  print 'Payload: ' + payload
  print 'Result: ' + requests.post(url=dps_url+dlm_pair_uri, cookies=cookie, data=payload, headers=headers, verify=False).content

  replicationPolicyName = 'hive-'+target_dataset_name+'-'+dlm_source_cluster_name+'-'+dlm_dest_cluster_name
  payload = '{"policyDefinition": {"name": "'+replicationPolicyName+'","type": "HIVE","sourceCluster": "'+dlm_source_cluster_dc+'$'+dlm_source_cluster_name+'","targetCluster": "'+dlm_dest_cluster_dc+'$'+dlm_dest_cluster_name+'","frequencyInSec": 3600,"sourceDataset": "'+target_dataset_name+'"},"submitType": "SUBMIT_AND_SCHEDULE"}'
  print 'Enabling replication policy: ' + replicationPolicyName + ' to: '+dps_url+dlm_clusters_uri+'/'+dlm_dest_cluster_id+'/policy/'+replicationPolicyName+'/submit'
  print 'Payload: ' + payload
  print 'Result: ' + requests.post(url=dps_url+dlm_clusters_uri+'/'+dlm_dest_cluster_id+'/policy/'+replicationPolicyName+'/submit', cookies=cookie, data=payload, headers=headers, verify=False).content

if sys.argv[1] == 'false':
  subprocess.call("CloudBreakArtifacts/recipes/load-logistics-dataset.sh")
