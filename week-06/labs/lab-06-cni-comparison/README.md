# Lab 6: CNI Plugin Comparison (CKA Extension)

**Time:** 45–55 minutes
**Objective:** Bootstrap kind clusters with three different CNIs, observe exactly what changes between them, and build a decision framework for choosing the right CNI in production.

---

## CKA Objectives Mapped

- Install a CNI plugin into a cluster that has no network provider
- Understand the role of the CNI in pod networking and NetworkPolicy enforcement
- Choose an appropriate CNI for a given scenario (exam knowledge question)

---

## Background: What a CNI Actually Does

When a pod is created, kubelet needs to do three things at the network level:

1. **Assign the pod an IP address** — from the cluster's pod CIDR
2. **Connect the pod to the cluster network** — so other pods can reach it
3. **Enforce NetworkPolicy rules** — if any exist that select this pod

The Container Network Interface (CNI) is the plugin that does all three. Kubernetes defines the interface; the CNI provides the implementation.

```
kubelet creates pod
    │
    └─► calls CNI plugin binary
              │
              ├─► allocates IP from pod CIDR  (IPAM)
              ├─► creates veth pair, bridges node interface
              └─► programs kernel rules for NetworkPolicy enforcement
```

**The critical operational fact:** Not all CNIs implement step 3. Some only do steps 1 and 2. If you apply a NetworkPolicy on a cluster whose CNI does not enforce policies, the objects exist in etcd but have zero effect on traffic. No error, no warning — traffic just flows.

This lab makes that difference visible.

---

## CNI Landscape

| CNI | Networking model | NetworkPolicy enforcement | L7 policy | Observability | Common use case |
|---|---|---|---|---|---|
| **kindnet** | Simple L2 bridge | **No** | No | Minimal | kind local dev, CNI-agnostic testing |
| **Flannel** | VXLAN overlay | No (needs Calico on top) | No | Minimal | Simplest multi-node overlay |
| **Calico** | BGP or VXLAN | **Yes** | No (base) | Moderate | Production bare-metal, VMs, air-gapped |
| **Cilium** | eBPF | **Yes** | **Yes** | Hubble (full flow visibility) | Cloud-native, service mesh, shared clusters |
| **Weave** | Mesh overlay | Yes | No | Moderate | Legacy; largely superseded |

The shared cluster in this course runs **Cilium**. This lab gives you the hands-on comparison with kindnet and Calico, and explains when you'd choose Cilium instead.

---

## Prerequisites

This lab spins up dedicated kind clusters. Each cluster uses CPU and memory from your host. Run clusters sequentially — create and delete before moving to the next.

Starter assets are in [`starter/`](./starter/):

- `kind-calico.yaml`
- `kind-cilium.yaml`
- `test-workloads.yaml`
- `deny-policy.yaml`

---

## Part 1: The Default CNI (kindnet)

Create a standard kind cluster. Unless you pass `disableDefaultCNI: true`, kind installs kindnet automatically.

```bash
kind create cluster --name cni-default
kubectl config use-context kind-cni-default
kubectl get nodes
```

Wait for the node to reach `Ready`. kindnet provides pod IPs immediately; pods can communicate across the cluster.

Deploy the test workloads — an nginx server and a curl client:

```bash
kubectl apply -f starter/test-workloads.yaml
kubectl wait --for=condition=Ready pod/server pod/client --timeout=60s
```

Verify connectivity from client to server:

```bash
kubectl exec client -- curl -s --max-time 5 http://server
```

You should see the nginx welcome page HTML — pods are communicating normally.

---

## Part 2: NetworkPolicy Does Nothing on kindnet

Now apply a NetworkPolicy that should deny all ingress to the server pod:

```bash
kubectl apply -f starter/deny-policy.yaml
kubectl get networkpolicy deny-server-ingress
kubectl describe networkpolicy deny-server-ingress
```

The policy exists. The spec is correct. Now test connectivity:

```bash
kubectl exec client -- curl -s --max-time 5 http://server
```

**The request still succeeds.** You'll see the nginx HTML again.

This is not a bug in your policy. kindnet does not implement NetworkPolicy enforcement. It assigns IPs and routes traffic between pods — nothing more. The API accepts the `NetworkPolicy` object, stores it in etcd, and does nothing with it, because kindnet never reads policy objects.

Run a final check to confirm the policy is syntactically valid:

```bash
kubectl describe networkpolicy deny-server-ingress
# Look for: "Allowing ingress traffic:" — it should say "0 Ingress rules blocking all ingress traffic"
# The description is accurate. kindnet just doesn't act on it.
```

Record this in your notes: **NetworkPolicy on kindnet = audit trail only**. It's a common source of "my NetworkPolicy doesn't work" incidents when a team moves a manifest from a Cilium/Calico cluster to a kindnet dev cluster, or uses Flannel without a NetworkPolicy-capable add-on.

---

## Part 3: What Happens Without Any CNI

Delete the default cluster and create one with the CNI disabled:

```bash
kind delete cluster --name cni-default

kind create cluster --name cni-calico --config starter/kind-calico.yaml
kubectl config use-context kind-cni-calico
```

Check node status:

```bash
kubectl get nodes
```

The node shows `NotReady`. Check why:

```bash
kubectl describe node cni-calico-control-plane | grep -A10 "Conditions:"
```

You'll see a condition like:

```
Ready  False  ...  KubeletNotReady  container runtime network not ready: NetworkReady=false
                                    reason:NetworkPluginNotReady message:Network plugin returns error...
```

Now try to deploy a pod:

```bash
kubectl run probe --image=nginx:1.27
kubectl get pods -w
```

The pod stays `Pending`. Check why:

```bash
kubectl describe pod probe | grep -A5 Events:
```

The pod can't be scheduled to a node without a working network plugin. The CNI is a hard requirement for pod networking, not a nice-to-have.

Delete the probe pod — you'll bring up the real workloads after installing Calico:

```bash
kubectl delete pod probe --ignore-not-found
```

---

## Part 4: Install Calico

Apply the Calico manifest. This installs the `calico-node` DaemonSet (handles routing and policy enforcement), the `calico-kube-controllers` Deployment (syncs Kubernetes resources into Calico's datastore), and the Calico CRDs:

```bash
kubectl apply -f https://raw.githubusercontent.com/projectcalico/calico/v3.29.0/manifests/calico.yaml
```

Wait for the Calico components to come up:

```bash
kubectl -n kube-system rollout status daemonset/calico-node --timeout=180s
kubectl -n kube-system rollout status deployment/calico-kube-controllers --timeout=120s
```

Check node status again:

```bash
kubectl get nodes
```

Both nodes should now show `Ready`. The CNI provided what kubelet needed.

Inspect the Calico DaemonSet to understand its configuration:

```bash
kubectl -n kube-system get daemonset calico-node -o yaml | grep -A5 "CALICO_IPV4POOL_CIDR"
```

This shows Calico's IPAM pool — the range it carves pod IPs from. It matches `192.168.0.0/16` because we set `podSubnet` in the kind config to match Calico's default. If they conflict, pods get IPs from the wrong range and routing breaks.

Look at what Calico installed:

```bash
kubectl -n kube-system get pods -l k8s-app=calico-node
kubectl -n kube-system get pods -l app=calico-kube-controllers
kubectl get crd | grep calico
```

The CRDs include `felixconfigurations`, `ippools`, `networkpolicies` (Calico's own extended variant), and more. Calico has its own policy model that extends Kubernetes NetworkPolicy — but for this lab we'll use standard `networking.k8s.io/v1` NetworkPolicy objects.

---

## Part 5: Calico Enforces NetworkPolicy

Deploy the same test workloads:

```bash
kubectl apply -f starter/test-workloads.yaml
kubectl wait --for=condition=Ready pod/server pod/client --timeout=90s
```

Verify pod IPs are in the Calico pool (192.168.x.x):

```bash
kubectl get pods -o wide
```

Test baseline connectivity — it should work:

```bash
kubectl exec client -- curl -s --max-time 5 http://server
```

Now apply the same deny policy you used in Part 2:

```bash
kubectl apply -f starter/deny-policy.yaml
```

Test again:

```bash
kubectl exec client -- curl -s --max-time 5 http://server
```

This time the connection hangs, then fails with a timeout or connection reset. The policy is being enforced.

To confirm it's the policy and not a pod issue:

```bash
# Server pod is still running and healthy
kubectl get pod server

# The policy is what changed
kubectl describe networkpolicy deny-server-ingress
```

Remove the policy and verify connectivity returns:

```bash
kubectl delete networkpolicy deny-server-ingress
kubectl exec client -- curl -s --max-time 5 http://server
```

Traffic flows again. Calico is reacting to NetworkPolicy creates and deletes in real time.

---

## Part 6: How Calico Enforces Policies

Calico enforces NetworkPolicy through its per-node agent: **Felix**. Felix runs inside the `calico-node` pod on each worker node and programs iptables (or eBPF, depending on version) rules based on policy objects it watches from the API server.

Look at what Felix programmed on the worker node:

```bash
# Exec into the calico-node pod on the worker
CALICO_NODE=$(kubectl -n kube-system get pods -l k8s-app=calico-node -o name | grep worker | head -1)
kubectl -n kube-system exec "$CALICO_NODE" -- iptables-save | grep -i cali | head -40
```

You'll see `cali-` prefixed chains — these are Calico's iptables chains that implement the traffic rules. Each NetworkPolicy becomes a set of iptables rules that the kernel evaluates for every packet.

Calico logs also show policy evaluation:

```bash
kubectl -n kube-system logs "$CALICO_NODE" -c calico-node --tail=50 | grep -i "policy\|felix" | head -20
```

---

## Part 7: Cilium — eBPF and Beyond NetworkPolicy

Clean up the Calico cluster before creating the Cilium one:

```bash
kind delete cluster --name cni-calico
```

Cilium replaces iptables with **eBPF** programs loaded directly into the Linux kernel. This removes iptables from the data path entirely — each packet evaluation goes through a BPF map lookup instead of traversing a chain of rules.

The differences over Calico:

| Capability | Calico | Cilium |
|---|---|---|
| Data plane | iptables / nftables | eBPF |
| NetworkPolicy | Standard `networking.k8s.io/v1` | Standard + `CiliumNetworkPolicy` (L7) |
| L7 policy (HTTP paths, gRPC) | No | Yes |
| Flow observability | No built-in | Hubble (per-pod flow visibility) |
| Service mesh | No | Cilium Mesh (mutual auth, encryption) |
| Scale (iptables rule growth) | Degrades linearly | Constant-time map lookups |
| Complexity | Moderate | Higher (requires kernel ≥ 5.4) |

The shared cluster in this course already runs Cilium. Use it to verify enforcement is working there too:

```bash
kubectl config use-context ziyotek-prod
kubectl -n kube-system get pods -l k8s-app=cilium | head
```

**Optional: Install Cilium in kind**

If the `cilium` CLI is available in your DevContainer:

```bash
which cilium && cilium version || echo "cilium CLI not available"
```

If available:

```bash
kind create cluster --name cni-cilium --config starter/kind-cilium.yaml
kubectl config use-context kind-cni-cilium

# Install Cilium (fetches and applies the correct manifests for the current kernel version)
cilium install
cilium status --wait

kubectl get nodes
kubectl apply -f starter/test-workloads.yaml
kubectl wait --for=condition=Ready pod/server pod/client --timeout=90s

# Verify connectivity
kubectl exec client -- curl -s --max-time 5 http://server

# Apply deny policy
kubectl apply -f starter/deny-policy.yaml
kubectl exec client -- curl -s --max-time 5 http://server  # should time out

# Cilium status shows active policies
cilium policy get

kind delete cluster --name cni-cilium
```

---

## Part 8: CKA CNI Selection Guide

The CKA exam includes knowledge-based questions: *"Which CNI would you use for..."* These are the patterns to know:

**"Install a network plugin so pods can communicate"**
→ Any CNI works. For exam scenarios on kubeadm clusters, Calico is the most commonly tested choice.
```bash
kubectl apply -f https://raw.githubusercontent.com/projectcalico/calico/v3.29.0/manifests/calico.yaml
```

**"NetworkPolicy is applied but not enforced"**
→ The CNI doesn't support enforcement. Switch to Calico or Cilium, or check that the existing CNI's policy enforcement is enabled.

**"Need L7 NetworkPolicy (allow GET /api but deny POST)"**
→ Cilium with `CiliumNetworkPolicy`. Standard NetworkPolicy is L3/L4 only.

**"Running on bare-metal servers with your own BGP routers"**
→ Calico with BGP mode. Calico can peer with upstream routers and advertise pod CIDRs directly — no overlay needed.

**"Need per-flow observability (who talked to who, rejected by which policy)"**
→ Cilium with Hubble. It provides flow-level metrics and UI without modifying applications.

**"Simplest possible setup for local development"**
→ kindnet (the default in kind). No additional steps, sufficient for testing workloads that don't rely on NetworkPolicy.

**"Cluster is using Flannel and NetworkPolicies aren't working"**
→ Flannel does not enforce NetworkPolicy in its base form. Install Calico as a NetworkPolicy controller alongside Flannel, or migrate to a CNI that provides full enforcement.

---

## Validation Checklist

You are done when:

- You observed that NetworkPolicy objects on a kindnet cluster have no effect on traffic
- You created a cluster with `disableDefaultCNI: true` and saw pods stuck in `Pending` without a CNI
- You installed Calico and saw nodes reach `Ready` and pods get IPs from `192.168.x.x`
- You applied the same deny policy on Calico and observed connections timing out
- You deleted the policy and confirmed traffic resumed
- You can explain in one sentence why kindnet ignores NetworkPolicy
- You can name the correct CNI for at least three of the CKA selection scenarios

---

## Cleanup

```bash
kind delete cluster --name cni-default   2>/dev/null || true
kind delete cluster --name cni-calico    2>/dev/null || true
kind delete cluster --name cni-cilium    2>/dev/null || true
kubectl config use-context ziyotek-prod  2>/dev/null || true
```

---

## Discovery Questions

1. **The missing enforcement:** You have a cluster running Flannel. A teammate applies a NetworkPolicy to block inter-pod traffic. Does it work? What is the fastest way to confirm whether it's being enforced, without reading the Flannel documentation?

2. **IPAM conflict:** You create a kind cluster with `podSubnet: "10.244.0.0/16"` and then install Calico without changing its default `CALICO_IPV4POOL_CIDR` (which defaults to `192.168.0.0/16`). What happens to pod IPs? What would you see in `kubectl get pods -o wide`?

3. **eBPF advantage:** A cluster with Calico has 5,000 pods and 200 NetworkPolicy objects. An iptables rule is added for every allowed flow. Why might this cause latency issues that the same cluster running Cilium with eBPF does not have?

4. **CKA scenario:** A kubeadm cluster has been bootstrapped but pods cannot communicate. `kubectl get nodes` shows both nodes `Ready`. What is the likely missing component, and what command would install Calico to fix it?

5. **Policy priority:** Calico has its own `CiliumNetworkPolicy`-equivalent: `NetworkPolicy.crd.projectcalico.org/v3`. If you apply both a `networking.k8s.io/v1` NetworkPolicy (allow) and a Calico v3 NetworkPolicy (deny) to the same pod, what is the precedence rule? *(Hint: look up Calico's policy ordering documentation.)*

---

## Reinforcement Scenario

- `33-jerry-wrong-cni-config` — CNI misconfiguration causing pod networking failure; diagnose from node status, pod events, and CNI logs

---

## Further Reading

- [Kubernetes Network Plugins](https://kubernetes.io/docs/concepts/extend-kubernetes/compute-storage-net/network-plugins/)
- [Calico installation docs](https://docs.tigera.io/calico/latest/getting-started/kubernetes/kind)
- [Cilium installation for kind](https://docs.cilium.io/en/stable/installation/kind/)
- [CNI specification](https://github.com/containernetworking/cni/blob/main/SPEC.md)
- [NetworkPolicy and CNI enforcement (Kubernetes docs)](https://kubernetes.io/docs/concepts/services-networking/network-policies/#prerequisites)
