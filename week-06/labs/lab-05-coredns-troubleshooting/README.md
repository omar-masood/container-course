# Lab 5: CoreDNS Troubleshooting Sprint (CKA Extension)

**Time:** 35 minutes  
**Objective:** Reproduce a CoreDNS failure, triage symptoms quickly, and restore service discovery.

---

## CKA Objectives Mapped

- Troubleshoot cluster component failures
- Troubleshoot DNS/service discovery symptoms
- Recover from CoreDNS configuration mistakes safely

---

## Background: CoreDNS and Cluster DNS

### How Kubernetes service discovery works

When you create a Service, Kubernetes automatically registers a DNS name for it. Any pod in the cluster can resolve `my-service.my-namespace.svc.cluster.local` without any extra configuration.

This works because every pod is configured (via `/etc/resolv.conf`) to use a DNS server running inside the cluster. That server is **CoreDNS**.

```
Pod wants to reach "redis"
    │
    ▼
/etc/resolv.conf: nameserver 10.96.0.10  ← CoreDNS ClusterIP
    │
    ▼
CoreDNS: looks up redis in cluster.local zone
    │  → found: redis.default.svc.cluster.local → 10.96.42.1
    ▼
Pod connects to 10.96.42.1 (the Service ClusterIP)
```

### What CoreDNS is

CoreDNS is a Go-based DNS server that replaced kube-dns in Kubernetes 1.13. It runs as a Deployment in `kube-system`, usually with 2 replicas. Its configuration lives in a ConfigMap called `coredns`, in a format called a **Corefile**.

A minimal Corefile:

```
cluster.local {
    kubernetes cluster.local in-addr.arpa ip6.arpa {
        pods insecure
        fallthrough in-addr.arpa ip6.arpa
    }
    cache 30
    loop
    reload
    forward . /etc/resolv.conf   ← upstream for non-cluster names
}
```

The `forward` directive controls where non-cluster DNS queries go (e.g. `google.com`). If this points at an invalid target, external resolution fails — which often looks like a total network outage.

### Why DNS failures are deceptive

DNS failure is one of the hardest cluster issues to diagnose because:

- Pods stay `Running` — DNS failure doesn't crash containers
- Error messages are misleading — apps report "connection refused" or "host not found", not "DNS is broken"
- It's cascading — if your app can't resolve `redis`, it reports a Redis error, not a DNS error

The fastest triage path is always: **can a pod resolve `kubernetes.default.svc.cluster.local`?** If not, DNS is the problem, not your app.

### Common CoreDNS failure modes

| Symptom | Likely cause |
|---|---|
| All DNS fails, including cluster names | CoreDNS pods crashed or OOMKilled |
| Cluster names resolve, external names fail | Bad `forward` upstream in Corefile |
| Intermittent timeouts | CoreDNS under-resourced; scale the deployment |
| `SERVFAIL` on specific names | Corefile syntax error or loop plugin triggered |

### The Corefile lives in a ConfigMap

This is both a feature and a footgun. You can update CoreDNS configuration with `kubectl edit configmap coredns -n kube-system` (or patch it), and CoreDNS reloads automatically (the `reload` plugin watches for changes). But a bad edit takes effect immediately across the whole cluster.

**Further reading:**
- [DNS for Services and Pods (Kubernetes docs)](https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/)
- [CoreDNS Customization](https://kubernetes.io/docs/tasks/administer-cluster/dns-custom-nameservers/)
- [Debugging DNS resolution](https://kubernetes.io/docs/tasks/administer-cluster/dns-debugging-resolution/)
- [CoreDNS project docs](https://coredns.io/manual/toc/)

---

## Prerequisites

Use local kind cluster only:

```bash
kubectl config use-context kind-lab
kubectl get nodes
```

Starter assets for this lab are in [`starter/`](./starter/):

- `dns-probe-pod.yaml`
- `inject-coredns-failure.sh`
- `restore-coredns.sh`
- `triage-checklist.md`

---

## Part 1: Baseline DNS Health

Create a probe pod and confirm DNS works before fault injection:

```bash
kubectl apply -f week-06/labs/lab-05-coredns-troubleshooting/starter/dns-probe-pod.yaml
kubectl wait --for=condition=Ready pod/dns-probe --timeout=60s
kubectl exec dns-probe -- nslookup kubernetes.default.svc.cluster.local
kubectl exec dns-probe -- nslookup svc-demo-clusterip.default.svc.cluster.local || true
```

---

## Part 2: Inject Failure

Run the injection script:

```bash
bash week-06/labs/lab-05-coredns-troubleshooting/starter/inject-coredns-failure.sh
```

This script:

- Backs up current CoreDNS config to `/tmp/coredns-backup.yaml`
- Rewrites upstream forwarding to an invalid target
- Restarts CoreDNS deployment

---

## Part 3: Triage Like an Incident

Use this sequence:

```bash
kubectl exec dns-probe -- nslookup kubernetes.default.svc.cluster.local || true
kubectl -n kube-system get pods -l k8s-app=kube-dns
kubectl -n kube-system logs deployment/coredns --tail=80
kubectl -n kube-system get configmap coredns -o yaml
kubectl get events -A --sort-by=.metadata.creationTimestamp | tail -40
```

Capture in your notes:

1. Symptom
2. Root cause evidence command
3. Fix command
4. Verification command

---

## Part 4: Restore CoreDNS

```bash
bash week-06/labs/lab-05-coredns-troubleshooting/starter/restore-coredns.sh
kubectl -n kube-system rollout status deployment/coredns --timeout=120s
```

Re-run DNS checks:

```bash
kubectl exec dns-probe -- nslookup kubernetes.default.svc.cluster.local
```

---

## Part 5: Verification Checklist

You are done when:

- DNS lookups fail during incident window
- You identify CoreDNS configuration as root cause
- DNS lookups succeed after restore
- Your notes include command-level evidence, not guesses

---

## Cleanup

```bash
kubectl delete pod dns-probe --ignore-not-found
rm -f /tmp/coredns-backup.yaml
```

---

## Reinforcement Scenario

- `jerry-coredns-loop`
