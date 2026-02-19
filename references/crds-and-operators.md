# CRDs and the Operator Pattern

**Understanding Custom Resources and Controllers in Kubernetes**

---

## You've Been Using CRDs This Whole Time

Every time you've worked with these resources, you were using **Custom Resource Definitions** (CRDs):

- `HTTPRoute` (Week 06 — Gateway API routing rules)
- `Application` (Week 08 — ArgoCD GitOps applications)
- `Gateway`, `GatewayClass` (Week 06 — shared ingress gateway)
- `ServiceMonitor` (Week 07 — Prometheus metric scraping, if used)

**The key insight:** These aren't built into Kubernetes. They're extensions that someone added to your cluster's API.

Base Kubernetes knows about: `Pod`, `Deployment`, `Service`, `ConfigMap`, `Secret`

Everything else? **Custom Resource Definition**.

---

## How to Explore CRDs

### List all CRDs in your cluster:

```bash
# See every CRD installed
kubectl get crd

# How many are there? (You'll be surprised)
kubectl get crd | wc -l
```

### Inspect a CRD you already know:

```bash
# Look at the HTTPRoute CRD definition
kubectl get crd httproutes.gateway.networking.k8s.io -o yaml | head -30

# Use kubectl explain on custom resources (same as built-in resources)
kubectl explain httproute
kubectl explain httproute.spec.rules
kubectl explain application.spec.source
```

### List instances of custom resources:

```bash
# All HTTPRoutes across namespaces
kubectl get httproutes -A

# All ArgoCD Applications
kubectl get applications -A -o wide

# Describe a specific custom resource
kubectl describe httproute uptime-kuma -n student-<your-name>-dev
```

### Find who owns a CRD:

```bash
# Which controller manages HTTPRoute?
kubectl get crd httproutes.gateway.networking.k8s.io -o jsonpath='{.spec.group}'

# What API version?
kubectl get crd httproutes.gateway.networking.k8s.io -o jsonpath='{.spec.versions[*].name}'
```

---

## What's an Operator?

An **operator** is the pattern of pairing a CRD with a controller:

- **CRD** = defines a new resource type (the "what")
- **Operator/Controller** = watches that CRD and acts on it (the "how")

### Examples you've used:

**ArgoCD Operator:**
- CRD: `Application` defines what should be deployed
- Controller: `argocd-application-controller` watches Applications and syncs clusters to match
- Pattern: Human writes `Application` YAML → ArgoCD reads it → ArgoCD deploys to cluster

**Cilium Gateway Operator:**
- CRDs: `Gateway`, `HTTPRoute` define routing rules
- Controller: Cilium agent programs eBPF to enforce routing
- Pattern: Human writes `HTTPRoute` YAML → Cilium reads it → eBPF rules get updated

**General Pattern:**
1. Human writes a custom resource (instance of a CRD)
2. Operator reads the custom resource
3. Operator does the work (creates Pods, updates configs, calls APIs, etc.)

---

## How to Install an Operator

When you ran `helm install` for ArgoCD, Vault, or Cilium, here's what happened:

1. **CRDs installed first** — extending the Kubernetes API with new resource types
2. **Controller deployed** — usually a Deployment or DaemonSet that watches the new CRDs
3. **You create instances** — write YAML for the custom resources

Example from Week 08 ArgoCD installation:
```bash
# This installed CRDs first, then the argocd-application-controller
helm install argocd argo/argo-cd -n argocd --create-namespace

# Then you created an Application (instance of the CRD)
kubectl apply -f applications/guestbook-app.yaml
```

---

## Troubleshooting Operators

When a custom resource isn't working:

### 1. Check the resource status:
```bash
kubectl describe application my-app -n argocd
# Look at Events and Conditions sections
```

### 2. Find the controller:
```bash
# ArgoCD example
kubectl get pods -n argocd | grep application-controller

# Generic approach - look for deployments with the CRD name
kubectl get deployments -A | grep -i application
```

### 3. Check controller logs:
```bash
kubectl logs deployment/argocd-application-controller -n argocd
```

### 4. Verify CRD is installed:
```bash
kubectl get crd applications.argoproj.io
```

---

## CKA Exam Relevance

The CKA may ask you to:

- **List CRDs** in a cluster: `kubectl get crd`
- **Inspect a custom resource**: `kubectl explain <custom-resource>`
- **Install an operator** via Helm and create an instance of its CRD
- **Troubleshoot** a custom resource that's not reconciling:
  - Check operator pods: `kubectl get pods -n <operator-namespace>`
  - Check logs: `kubectl logs <operator-pod>`
  - Check events: `kubectl describe <custom-resource>`

---

## Quick Reference Commands

```bash
# List all CRDs
kubectl get crd

# Explore a specific CRD
kubectl explain <resource-name>
kubectl get <resource-name> -A

# Find the controller for a CRD
kubectl get crd <crd-name> -o yaml | grep -A5 -B5 controller

# Common operator troubleshooting
kubectl describe <custom-resource> <name> -n <namespace>
kubectl get pods -n <operator-namespace>
kubectl logs <operator-pod> -n <operator-namespace>
```

---

## Key Takeaways

- CRDs extend Kubernetes with new resource types
- Operators are controllers that act on custom resources
- You've been using both since Week 06 without realizing it
- The same `kubectl` patterns work: `get`, `describe`, `explain`, `logs`
- When custom resources don't work, check the operator pods and logs