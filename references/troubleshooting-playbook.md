# CKA Troubleshooting Playbook

This is your field manual for systematic incident triage during the CKA exam. Keep this mental model available and drill these patterns until they become automatic reflexes.

## Runbook: The Node Looks Sick

**When to use this:** Node shows NotReady status, workloads stuck Pending on specific nodes, or node capacity issues.

**Triage sequence:**
1. `kubectl get nodes -o wide` — check Ready status, version, OS, internal/external IPs
2. `kubectl describe node <node-name>` — look for conditions (disk pressure, memory pressure, PID pressure, network unavailable), taints, capacity vs allocatable resources
3. `kubectl get events --field-selector involvedObject.kind=Node --sort-by='.lastTimestamp'` — look for kubelet registration failures, resource exhaustion, taint application events
4. `docker exec <node-name> systemctl status kubelet` — verify kubelet service is active and running
5. `docker exec <node-name> journalctl -u kubelet --since="15 minutes ago" --no-pager` — check recent kubelet logs for errors

**Common root causes:**
- kubelet service stopped/crashed (systemctl shows inactive/failed)
- Node resource exhaustion (memory/disk pressure conditions set to True)
- Node taints blocking pod scheduling (NoSchedule/NoExecute effects)
- Network connectivity issues preventing kubelet from reaching API server

**Fix patterns:**
```bash
# Restart kubelet service
docker exec <node-name> systemctl start kubelet

# Remove blocking taint
kubectl taint node <node-name> <taint-key>:<effect>-

# Cordon node for maintenance if resource exhausted
kubectl cordon <node-name>

# Force pod eviction from unhealthy node
kubectl drain <node-name> --ignore-daemonsets --force --delete-emptydir-data
```

**Verification:**
```bash
kubectl get nodes -o wide
# Look for Ready=True status, no pressure conditions

kubectl run test-schedule --image=registry.k8s.io/pause:3.10 --restart=Never
kubectl get pod test-schedule -o wide
# Verify pod schedules successfully to recovered node
kubectl delete pod test-schedule
```

**Drill scenarios:**
- `gymctl start jerry-node-notready-kubelet` — kubelet stopped during maintenance
- `gymctl start jerry-forgot-resources` — resource requests exceed node capacity
- `gymctl start jerry-node-drain-pdb-blocked` — drain blocked by PodDisruptionBudget

---

## Runbook: A Control Plane Component Is Down

**When to use this:** Static pods not Running in kube-system, API server unreachable, scheduler/controller-manager failures.

**Triage sequence:**
1. `kubectl get pods -n kube-system` — identify which component pods are not Running
2. `kubectl describe pod <component-pod> -n kube-system` — check container status, recent events, restart counts
3. `docker exec <control-plane-node> ls -la /etc/kubernetes/manifests/` — verify static pod manifests exist
4. `docker exec <control-plane-node> cat /etc/kubernetes/manifests/<component>.yaml` — inspect manifest for syntax errors, bad flags, wrong paths
5. `docker exec <control-plane-node> crictl ps -a` — check container runtime view of component containers

**Common root causes:**
- Invalid flags or typos in static pod manifest files
- Wrong file paths in kubeconfig/certificate references
- Insufficient resources allocated to control plane components
- Certificate expiration or permission issues

**Fix patterns:**
```bash
# Fix manifest syntax error or bad flag
docker exec <control-plane-node> vi /etc/kubernetes/manifests/kube-scheduler.yaml

# Restart component by temporarily moving manifest away and back
docker exec <control-plane-node> mv /etc/kubernetes/manifests/kube-scheduler.yaml /tmp/
sleep 10
docker exec <control-plane-node> mv /tmp/kube-scheduler.yaml /etc/kubernetes/manifests/

# Check component logs for detailed error messages
docker exec <control-plane-node> crictl logs <container-id>
```

**Verification:**
```bash
kubectl get pods -n kube-system
# All control plane pods should show Running status

kubectl get componentstatuses 2>/dev/null || kubectl get --raw='/readyz' | jq .
# API server health check should succeed

kubectl run verify-scheduler --image=registry.k8s.io/pause:3.10 --restart=Never
kubectl get pod verify-scheduler -o jsonpath='{.spec.nodeName}'
# New pod should get scheduled (not stuck Pending)
kubectl delete pod verify-scheduler
```

**Drill scenarios:**
- `gymctl start jerry-coredns-loop` — CoreDNS forwarding loop configuration
- `gymctl start jerry-etcd-snapshot-missing` — etcd data corruption requiring restore
- `gymctl start jerry-static-pod-misconfigured` — scheduler manifest with bad flags
- `gymctl start 37-jerry-scheduler-missing` — scheduler absent from kube-system due to manifest breakage

---

## Runbook: Pods Won't Schedule

**When to use this:** Pods stuck in Pending state, scheduler reporting placement failures, resource quotas exceeded.

**Triage sequence:**
1. `kubectl get pods -A --field-selector status.phase=Pending` — list all Pending pods cluster-wide
2. `kubectl describe pod <pending-pod>` — check Events section for scheduling failure reasons
3. `kubectl get nodes --show-labels` — verify node labels match any nodeSelector requirements
4. `kubectl describe nodes` — check for taints, capacity constraints, unschedulable status
5. `kubectl top nodes` — verify actual resource usage vs requests (requires metrics-server)

**Common root causes:**
- Node taints without matching pod tolerations (NoSchedule effect)
- nodeSelector/nodeAffinity requirements not satisfied by available nodes
- Insufficient CPU/memory resources on schedulable nodes
- PodDisruptionBudget preventing drain operations during maintenance

**Fix patterns:**
```bash
# Remove blocking taint from node
kubectl taint node <node-name> <taint-key>:<effect>-

# Add toleration to deployment
kubectl patch deployment <name> -p '{"spec":{"template":{"spec":{"tolerations":[{"key":"<taint-key>","operator":"Equal","value":"<taint-value>","effect":"<effect>"}]}}}}'

# Remove nodeSelector constraint
kubectl patch deployment <name> --type='json' -p='[{"op": "remove", "path": "/spec/template/spec/nodeSelector"}]'

# Uncordon previously cordoned node
kubectl uncordon <node-name>
```

**Verification:**
```bash
kubectl get pods -o wide --field-selector status.phase=Running
# Previously Pending pods should now show Running with assigned nodes

kubectl describe pod <previously-pending-pod>
# Events should show successful scheduling, not FailedScheduling
```

**Drill scenarios:**
- `gymctl start jerry-pod-unschedulable-taint` — pods can't tolerate node taints
- `gymctl start jerry-node-drain-pdb-blocked` — PDB prevents pod eviction during drain
- `gymctl start jerry-forgot-resources` — resource requests exceed available capacity

---

## Runbook: Who's Eating All the Resources

**When to use this:** Cluster feels slow, new deployments can't scale, nodes approaching resource limits.

**Triage sequence:**
1. `kubectl top nodes` — identify nodes with high CPU/memory utilization percentages
2. `kubectl top pods -A --sort-by=memory` — find top memory consumers across all namespaces
3. `kubectl top pods -A --sort-by=cpu` — find top CPU consumers across all namespaces
4. `kubectl describe node <high-usage-node>` — check allocated resources vs capacity, identify resource hogs
5. `kubectl get pods -A -o=jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{.metadata.name}{"\t"}{.spec.containers[*].resources.requests.memory}{"\n"}{end}' | sort -k3 -hr` — list pods by memory requests

**Common root causes:**
- Deployment with excessive resource requests hogging node capacity
- Missing resource limits allowing containers to consume more than expected
- Resource leak in application causing memory or CPU spike
- metrics-server not installed/working (top commands fail)

**Fix patterns:**
```bash
# Install metrics-server in kind cluster
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
kubectl patch deployment metrics-server -n kube-system --type='json' -p='[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'

# Reduce resource hog's requests
kubectl patch deployment <resource-hog> -p '{"spec":{"template":{"spec":{"containers":[{"name":"<container>","resources":{"requests":{"cpu":"100m","memory":"128Mi"},"limits":{"cpu":"250m","memory":"256Mi"}}}]}}}}'

# Scale down resource-intensive deployment temporarily
kubectl scale deployment <name> --replicas=1
```

**Verification:**
```bash
kubectl top nodes
# Node utilization should be more balanced, no nodes >80% memory/CPU

kubectl get pods -A --field-selector status.phase=Running
# All expected workloads should be Running, not Pending due to resource constraints

kubectl describe deployment <fixed-deployment>
# Resource requests should be reasonable (<500m CPU, <512Mi memory per container)
```

**Drill scenarios:**
- `gymctl start jerry-resource-hog-hunt` — excessive resource requests blocking scheduling
- `gymctl start jerry-forgot-resources` — pods competing for limited node resources

---

## Runbook: The Pod Has Multiple Containers and One Is Broken

**When to use this:** Pod shows Init:Error, Init:CrashLoopBackOff, or Running but not Ready with multiple containers.

**Triage sequence:**
1. `kubectl get pods -o wide` — identify pods with low Ready count (e.g., 2/3 Ready)
2. `kubectl describe pod <multi-container-pod>` — check Init Containers and Containers sections for failed states
3. `kubectl logs <pod> -c <init-container>` — read logs from specific init container
4. `kubectl logs <pod> -c <sidecar-container> --previous` — get logs from previous crash if container restarting
5. `kubectl get pod <pod> -o jsonpath='{.status.containerStatuses[*].name}' && kubectl get pod <pod> -o jsonpath='{.status.containerStatuses[*].state}'` — list container names and their current states

**Common root causes:**
- Init container failing due to missing dependency (ConfigMap, Service, external resource)
- Sidecar container crash-looping due to configuration error
- Shared volume mount issues between containers
- Resource limits causing container OOMKill in multi-container setup

**Fix patterns:**
```bash
# Create missing ConfigMap that init container needs
kubectl create configmap <name> --from-literal=key=value

# Create missing Service that init container tries to reach
kubectl expose deployment <target> --port=8080 --target-port=8080

# Fix init container command to not require missing dependency
kubectl patch deployment <name> --type='json' -p='[{"op":"replace","path":"/spec/template/spec/initContainers/0/command","value":["sh","-c","echo ready"]}]'

# Delete pod to trigger recreation with fixes
kubectl delete pod <pod>
```

**Verification:**
```bash
kubectl get pods -o wide
# Pod should show all containers Ready (e.g., 3/3 Ready), status Running

kubectl describe pod <fixed-pod>
# Init Containers section should show all containers Terminated with exit code 0
# Containers section should show all containers Running

kubectl logs <pod> -c <previously-failing-container>
# Logs should show successful startup, no error messages
```

**Drill scenarios:**
- `gymctl start jerry-container-log-mystery` — init container failing due to missing service
- `gymctl start 34-jerry-init-container-stuck` — pod stuck in Init:CrashLoopBackOff from broken init script

---

## Runbook: I Can't Reach the Service

**When to use this:** Service endpoints empty, DNS resolution failing, networking connectivity issues between pods.

**Triage sequence:**
1. `kubectl get svc <service-name> -o wide` — verify service exists and has correct selector, ports, type
2. `kubectl get endpoints <service-name>` — check if service has backing pod endpoints
3. `kubectl get pods -l <service-selector> -o wide` — verify pods matching service selector are Running and Ready
4. `kubectl run debug --image=busybox:1.36 -it --rm -- nslookup <service-name>.<namespace>.svc.cluster.local` — test DNS resolution
5. `kubectl exec debug -- wget -qO- <service-name>:<port>` — test actual connectivity to service

**Common root causes:**
- Service selector doesn't match pod labels (endpoints will be empty)
- DNS resolution broken due to CoreDNS misconfiguration
- NetworkPolicy blocking pod-to-service communication
- Wrong Service type (ClusterIP vs NodePort) for intended access pattern

**Fix patterns:**
```bash
# Fix service selector to match pod labels
kubectl patch service <name> -p '{"spec":{"selector":{"app":"<correct-label>"}}}'

# Restore CoreDNS to working configuration
kubectl -n kube-system get configmap coredns -o yaml > coredns-backup.yaml
kubectl -n kube-system apply -f coredns-backup.yaml
kubectl -n kube-system rollout restart deployment/coredns

# Allow traffic through NetworkPolicy
kubectl label namespace <source-ns> name=<source-ns>  # if NetworkPolicy uses namespaceSelector

# Change Service type for external access
kubectl patch service <name> -p '{"spec":{"type":"NodePort"}}'
```

**Verification:**
```bash
kubectl get endpoints <service-name>
# Should show IP addresses of backend pods, not empty

kubectl run dns-test --image=busybox:1.36 --restart=Never --rm -it -- nslookup <service>.<namespace>.svc.cluster.local
# Should return service ClusterIP, not NXDOMAIN

kubectl run connectivity-test --image=busybox:1.36 --restart=Never --rm -it -- wget -qO- <service>:<port>
# Should return actual response from backend pods, not connection refused
```

**Drill scenarios:**
- `gymctl start jerry-broken-service` — service selector mismatch with pod labels
- `gymctl start jerry-nodeport-mystery` — wrong service type for intended access
- `gymctl start jerry-broken-ingress-host` — ingress routing issues to backing service
- `gymctl start jerry-networkpolicy-dns` — NetworkPolicy blocking DNS or service traffic
- `gymctl start jerry-gateway-route-detached` — Gateway API routing configuration issues
- `gymctl start jerry-coredns-loop` — CoreDNS misconfiguration breaking cluster DNS
