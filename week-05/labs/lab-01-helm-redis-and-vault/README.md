# Lab 1: Helm for Vault, Manifests for Redis

**Time:** 30 minutes  
**Objective:** Learn Helm by installing Vault, then deploy Redis from scratch with plain manifests

---

## The Two Approaches - Helm vs. Manifest.yaml

Kubernetes manifests can be a real pain in the butt. YAML is finicky, the schemas are complex and ever evolving. Installing and maintaining complex application on Kubernetes is a chore and filled with many pain points. The community surrounding Kubernetes came up with a different approach to manifest creation. That project is called Helm - https://helm.sh. Think of Helm like a package manager for Kubernetes deplyments. Don't want to configure a MySQL service, deployment, pvc, and statefulset from scratch every time? I don't blame you. Helm allows us to install software no matter how complex. It takes a simpler approach to installing, upgrading, and removing applications from within a cluster. 

Not everything belongs in a Helm chart, and not everything should be hand-written YAML. This lab teaches you when to use which.

**Helm** is the right tool when you're deploying software you didn't write and don't want to maintain — software with dozens of configuration knobs, RBAC rules, sidecar injectors, and upgrade procedures that the maintainers have already figured out. Vault is a perfect example: it has a server, an agent injector, service accounts, policies, and HA modes. The HashiCorp team publishes a chart that wires all of this up correctly. You provide 10 lines of values, Helm generates 200+ lines of battle-tested manifests.

**Plain manifests** are the right tool when you understand the software and the deployment is simple. Redis in standalone mode is a container, a service, and a volume. Four files. You know exactly what each line does because you wrote it. No template magic, no hidden defaults, no wondering what `helm upgrade` will change under the hood.

```
┌─────────────────────────────────┐     ┌─────────────────────────────────┐
│          Use Helm When          │     │     Use Plain Manifests When    │
│                                 │     │                                 │
│  Complex software you didn't    │     │  Simple services you understand │
│  write (Vault, Prometheus,      │     │  (Redis standalone, your app,   │
│  cert-manager, ArgoCD)          │     │  nginx, postgres single-node)   │
│                                 │     │                                 │
│  Dozens of config options       │     │  A few files, clear structure   │
│  Upgrade procedures matter      │     │  You own every line             │
│  Community maintains templates  │     │  Changes go through Git review  │
│                                 │     │                                 │
│  You're a consumer              │     │  You're the author              │
└─────────────────────────────────┘     └─────────────────────────────────┘
```

By the end of this lab, you'll have Vault (via Helm) and Redis (via manifests) running on your local kind cluster, ready for Lab 2 where your app connects to both.

---

## Part 1: Helm Basics

Helm is a package manager for Kubernetes — think `apt install` but for your cluster. A **chart** is a package of templated Kubernetes manifests. A **release** is an installed instance of a chart. **Values** are your configuration overrides.

### Install Helm

**In Codespaces:** Helm is already installed in your devcontainer.

**On your VM:**

```bash
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
helm version
```

### Add Repositories

Charts are published to repositories, like Docker registries for Kubernetes packages:

```bash
# HashiCorp publishes the official Vault chart
helm repo add hashicorp https://helm.releases.hashicorp.com

# Update your local chart index
helm repo update
```

### Search for Charts

```bash
# What does HashiCorp publish?
helm search repo hashicorp

# See available versions of the Vault chart
helm search repo hashicorp/vault --versions | head -10
```

---

## Part 2: Install Vault with Helm

### Look Before You Leap

Before installing anything, see what a chart will actually create:

```bash
# Show the chart's default values — this is its full configuration surface
helm show values hashicorp/vault | head -100
```

That's a lot of options. You don't need most of them. A values file lets you override just what you care about.

### Examine the Values File

The starter directory has a values file for Vault in dev mode:

```bash
cat starter/vault-values.yaml
```

```yaml
server:
  dev:
    enabled: true
    devRootToken: "root"

  resources:
    requests:
      memory: "64Mi"
      cpu: "50m"
    limits:
      memory: "256Mi"
      cpu: "200m"

injector:
  enabled: true
  resources:
    requests:
      memory: "64Mi"
      cpu: "50m"
    limits:
      memory: "256Mi"
      cpu: "200m"
```

Dev mode means Vault runs in-memory, unsealed by default, with a known root token. Never do this in production — but it's perfect for learning.

### Preview What Helm Will Create

Before installing, you can see the exact Kubernetes manifests Helm would generate:

```bash
helm template vault hashicorp/vault -f starter/vault-values.yaml | head -200
```

Scroll through that output. You'll see ServiceAccounts, ClusterRoleBindings, ConfigMaps, Services, a StatefulSet for the server, a Deployment for the injector, and more. This is what you'd have to write by hand without Helm.

> **`helm template` vs `helm install --dry-run`:** `helm template` renders locally without talking to your cluster. `helm install --dry-run` renders server-side and validates against your cluster's API. For previewing, `template` is faster. For validation, use `--dry-run`.

### Install It

```bash
helm install vault hashicorp/vault -f starter/vault-values.yaml
```

Breaking this down:
- `helm install` — install a chart
- `vault` — the **release name** (you choose this, it prefixes created resources)
- `hashicorp/vault` — the chart (`repo/chart-name`)
- `-f starter/vault-values.yaml` — override default values with your file

Helm prints a summary with post-install notes. Chart authors put useful connection instructions here — read them.

### Explore What Helm Created

```bash
# List all Helm releases
helm list

# See what Kubernetes resources the chart created
kubectl get all -l app.kubernetes.io/instance=vault

# The Vault server pod
kubectl get pods -l app.kubernetes.io/name=vault

# The Vault Agent Injector (we'll use this in a later week)
kubectl get pods -l app.kubernetes.io/name=vault-agent-injector

# Secrets Helm stored
kubectl get secrets -l app.kubernetes.io/instance=vault

# The actual manifests Helm applied
helm get manifest vault | head -50
```

Count the resources. That's dozens of Kubernetes objects — RBAC, services, health checks, pod disruption budgets — all generated from your 15-line values file.

### Test the Connection

```bash
# Exec into the Vault pod and run commands directly
kubectl exec -it vault-0 -- vault status

# Write a test secret
kubectl exec -it vault-0 -- vault kv put secret/test message="hello from vault"

# Read it back
kubectl exec -it vault-0 -- vault kv get secret/test
```

You now have a running Vault instance. We'll use it for secret management in a later week. For now, the point is: Helm let you deploy a complex piece of infrastructure without writing a single manifest.

### Helm Lifecycle Commands

Practice these — you'll use them constantly:

```bash
# What values did you use?
helm get values vault

# ALL values including defaults you didn't override
helm get values vault --all | head -50

# Release history (revisions)
helm history vault

# Upgrade: change a value and re-apply
# (e.g., increase memory limit in vault-values.yaml, then:)
# helm upgrade vault hashicorp/vault -f starter/vault-values.yaml

# Rollback to a previous revision
# helm rollback vault 1

# Uninstall (we won't do this — we need Vault running)
# helm uninstall vault
```

---

## Part 3: Deploy Redis with Plain Manifests

Now the other approach. Redis in standalone mode is simple enough that you should own every line. No chart, no templates — just Kubernetes objects you write yourself.

You'll create four resources:

```
┌──────────────────────────────────────────────────────┐
│                   Your Redis Stack                    │
│                                                       │
│  ┌─────────────┐  ConfigMap: redis-config             │
│  │ redis.conf  │  (custom Redis configuration)        │
│  └──────┬──────┘                                      │
│         │ mounted as file                             │
│  ┌──────▼──────────────────────────────────────────┐  │
│  │  StatefulSet: redis                             │  │
│  │  ┌────────────────────────────┐                 │  │
│  │  │  Pod: redis-0              │                 │  │
│  │  │  image: redis:7-alpine     │                 │  │
│  │  │  port: 6379                │                 │  │
│  │  │  /data ──► PVC (256Mi)     │                 │  │
│  │  └────────────────────────────┘                 │  │
│  └─────────────────────────────────────────────────┘  │
│                                                       │
│  ┌─────────────────┐  Secret: redis-credentials       │
│  │  REDIS_PASSWORD  │  (auth password)                │
│  └─────────────────┘                                  │
│                                                       │
│  ┌─────────────────┐  Service: redis                  │
│  │  ClusterIP       │  (stable endpoint for pods)     │
│  │  port: 6379      │                                 │
│  └─────────────────┘                                  │
└──────────────────────────────────────────────────────┘
```

### Why a StatefulSet Instead of a Deployment?

Deployments are for stateless workloads — your app pods are interchangeable. StatefulSets are for stateful workloads where:

- Pods need **stable identities** (the pod is always `redis-0`, not `redis-7f4b8c9d-xk2j9`)
- Pods need **stable storage** (the same PVC reattaches if the pod restarts)
- Pods may need **ordered startup and shutdown**

Redis stores data on disk. If the pod restarts, it needs to find its data again. A StatefulSet guarantees that `redis-0` always gets the same PVC, even after deletion and recreation.

Read more: [StatefulSet documentation](https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/)

```bash
# Compare the two
kubectl explain statefulset.spec --recursive | head -30
kubectl explain deployment.spec --recursive | head -30
```

The key difference is `volumeClaimTemplates` — a StatefulSet can automatically create a PVC for each pod.

### Write the Manifests

Create a directory for your Redis manifests and work through each file. Use `kubectl explain` to understand every field — don't just copy and paste.

```bash
mkdir -p redis-manifests
cd redis-manifests
```

#### ConfigMap: Redis Configuration

Redis reads its configuration from a file. A ConfigMap lets you mount that file into the container without baking it into the image.

> **Discovery:** Check the [official Redis configuration docs](https://redis.io/docs/latest/operate/oss_and_stack/management/config/) to understand what these settings do. What does `appendonly yes` mean for data durability? What's the difference between RDB snapshots and AOF persistence?

Create `redis-configmap.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: redis-config
data:
  redis.conf: |
    # Require password authentication
    requirepass redis-lab-password

    # Persistence — append-only file for durability
    appendonly yes
    appendfsync everysec

    # Memory limit appropriate for learning environment
    maxmemory 128mb
    maxmemory-policy allkeys-lru

    # Bind to all interfaces (required in containers)
    bind 0.0.0.0

    # Disable dangerous commands in shared environments
    rename-command FLUSHALL ""
    rename-command FLUSHDB ""
```

```bash
kubectl apply -f redis-configmap.yaml
```

**Why put the password in the config file?** In this lab, it's intentional duplication — the password appears in both the ConfigMap (for Redis to read at startup) and a Secret (for your app to read as an env var). In production, you'd use Vault or an init container to inject the password at runtime. We'll fix this in a later week. For now, focus on the mechanics.

#### Secret: Redis Password

Your application needs the Redis password as an environment variable. Create `redis-secret.yaml`:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: redis-credentials
type: Opaque
stringData:
  REDIS_PASSWORD: "redis-lab-password"
```

```bash
kubectl apply -f redis-secret.yaml
```

> **This should bother you.** The password is sitting in plaintext in a YAML file. Anyone who clones your repo reads it. Base64 encoding (what Kubernetes stores internally) is not encryption. We're going to commit this sin today and fix it properly in a later week with Vault or Sealed Secrets. Feeling uncomfortable about plaintext secrets in Git is the correct instinct.

#### StatefulSet: The Redis Pod

This is the main resource. Create `redis-statefulset.yaml`:

> **Try scaffolding first.** Before looking at the manifest below, try generating a starting point:
> ```bash
> kubectl create statefulset redis --image=redis:7-alpine --dry-run=client -o yaml
> ```
> The output won't have everything you need (no volume mounts, no config), but it gives you the skeleton. Compare it to what's below to see what you need to add.

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: redis
  labels:
    app: redis
spec:
  serviceName: redis
  replicas: 1
  selector:
    matchLabels:
      app: redis
  template:
    metadata:
      labels:
        app: redis
    spec:
      containers:
      - name: redis
        image: redis:7-alpine
        command: ["redis-server", "/etc/redis/redis.conf"]
        ports:
        - containerPort: 6379
          name: redis
        volumeMounts:
        - name: redis-data
          mountPath: /data
        - name: redis-config
          mountPath: /etc/redis
        resources:
          requests:
            memory: "64Mi"
            cpu: "50m"
          limits:
            memory: "256Mi"
            cpu: "200m"
        readinessProbe:
          exec:
            command: ["redis-cli", "-a", "redis-lab-password", "ping"]
          initialDelaySeconds: 5
          periodSeconds: 10
        livenessProbe:
          exec:
            command: ["redis-cli", "-a", "redis-lab-password", "ping"]
          initialDelaySeconds: 10
          periodSeconds: 15
      volumes:
      - name: redis-config
        configMap:
          name: redis-config
  volumeClaimTemplates:
  - metadata:
      name: redis-data
    spec:
      accessModes: ["ReadWriteOnce"]
      resources:
        requests:
          storage: 256Mi
```

Walk through this:

- **`serviceName: redis`** — Required for StatefulSets. Links to a headless Service for DNS.
- **`command: ["redis-server", "/etc/redis/redis.conf"]`** — Tells Redis to use our ConfigMap-mounted configuration file instead of defaults.
- **`volumeMounts`** — Two mounts: `/data` for persistent storage (from the PVC), `/etc/redis` for the config file (from the ConfigMap).
- **`volumeClaimTemplates`** — The StatefulSet creates a PVC named `redis-data-redis-0` automatically. If the pod restarts, it reattaches to the same PVC.
- **`readinessProbe` / `livenessProbe`** — Uses `redis-cli ping` to check if Redis is responsive. The `-a` flag passes the password since we enabled authentication.
- **`image: redis:7-alpine`** — The official Redis image. Alpine variant for smaller size. No Bitnami wrapper, no custom entrypoint — just Redis.

```bash
kubectl apply -f redis-statefulset.yaml
```

Watch it come up:

```bash
kubectl get pods -w
```

Press `Ctrl+C` once `redis-0` shows `1/1 Running`.

> **Notice the pod name.** It's `redis-0`, not `redis-7f4b8c9d-xk2j9`. StatefulSet pods get predictable, sequential names. If you scaled to 3 replicas, you'd get `redis-0`, `redis-1`, `redis-2`. This is what "stable identity" means.

#### Service: Stable Network Endpoint

Your app needs a DNS name to reach Redis. Create `redis-service.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: redis
  labels:
    app: redis
spec:
  selector:
    app: redis
  ports:
  - port: 6379
    targetPort: 6379
    name: redis
  clusterIP: None
```

**`clusterIP: None`** makes this a **headless Service**. Instead of a single virtual IP that load-balances, it creates a DNS record that resolves directly to the pod IPs. For a single-replica stateful service, this means `redis.default.svc.cluster.local` resolves to the IP of `redis-0`. StatefulSets require a headless Service for their DNS-based stable identities.

> **Discovery:** Read the [headless Services documentation](https://kubernetes.io/docs/concepts/services-networking/service/#headless-services). How does DNS resolution differ from a normal ClusterIP Service? What DNS record does `redis-0.redis.default.svc.cluster.local` resolve to?

```bash
kubectl apply -f redis-service.yaml
```

---

## Part 4: Verify Redis Is Working

### Check the Resources

```bash
# StatefulSet
kubectl get statefulset redis

# Pod with stable name
kubectl get pods -l app=redis

# PVC created by the volumeClaimTemplate
kubectl get pvc

# Service
kubectl get service redis

# Everything together
kubectl get all -l app=redis
kubectl get pvc -l app=redis
```

### Connect and Test

```bash
# Exec into the Redis pod
kubectl exec -it redis-0 -- redis-cli -a redis-lab-password

# Inside the redis-cli:
ping
# → PONG

set testkey "hello from kubernetes"
get testkey
# → "hello from kubernetes"

incr visitor-count
incr visitor-count
incr visitor-count
get visitor-count
# → "3"

exit
```

### Prove Data Survives a Restart

This is the whole point of PVCs. Delete the Redis pod and verify data persists:

```bash
# Kill the pod
kubectl delete pod redis-0

# Watch the StatefulSet recreate it (same name, same PVC)
kubectl get pods -w
```

Wait for `redis-0` to be `Running` again, then:

```bash
# Check — the data is still there
kubectl exec -it redis-0 -- redis-cli -a redis-lab-password get visitor-count
# → "3"

kubectl exec -it redis-0 -- redis-cli -a redis-lab-password get testkey
# → "hello from kubernetes"
```

The pod died and was recreated. The StatefulSet gave it the same name (`redis-0`) and reattached the same PVC (`redis-data-redis-0`). Redis loaded its AOF file from `/data` on startup and recovered all the data.

This is why StatefulSets exist. A Deployment would create a pod with a random name and a new empty PVC.

### Test DNS Resolution

From another pod, verify that the Redis Service name resolves:

```bash
kubectl run dns-test --rm -it --image=busybox:1.36 -- nslookup redis
```

You should see `redis.default.svc.cluster.local` resolve to the IP of `redis-0`. This is the hostname your app will use in Lab 2 — no hardcoded IPs, just the Service name.

---

## Part 5: Compare What You Built

Take stock of your cluster:

```bash
echo "=== Helm Release ==="
helm list

echo ""
echo "=== Vault (installed by Helm) ==="
kubectl get all -l app.kubernetes.io/instance=vault

echo ""
echo "=== Redis (your manifests) ==="
kubectl get all -l app=redis
kubectl get pvc -l app=redis
kubectl get configmap redis-config
kubectl get secret redis-credentials
```

Two backing services, two approaches:

| | Vault (Helm) | Redis (Manifests) |
|---|---|---|
| **Installed with** | `helm install` | `kubectl apply -f` |
| **Config** | `values.yaml` (15 lines) | 4 YAML files (~80 lines) |
| **Resources created** | ~15 (SA, RBAC, ConfigMap, StatefulSet, Service, Injector Deployment, ...) | 4 (ConfigMap, Secret, StatefulSet, Service) |
| **You understand every line?** | Probably not | Yes |
| **Upgrades** | `helm upgrade` | Edit YAML + `kubectl apply` |
| **Rollback** | `helm rollback` | `git revert` + `kubectl apply` |

Neither approach is "better." They're tools for different jobs. Complex third-party software → Helm. Simple services you own → manifests. Your student app will always be plain manifests. The monitoring stack on the shared cluster? That's Helm all the way.

---

## Part 6: Take Stock of Your Manifests

Your `redis-manifests/` directory should contain:

```
redis-manifests/
├── redis-configmap.yaml
├── redis-secret.yaml
├── redis-statefulset.yaml
└── redis-service.yaml
```

Keep these files — you'll reuse them in Lab 3 when you push Redis to the shared cluster alongside your updated app.

---

## Checkpoint ✅

Before moving on, verify:

- [ ] `helm list` shows the `vault` release
- [ ] Vault pod is running: `kubectl get pods -l app.kubernetes.io/name=vault`
- [ ] You can write and read secrets from Vault via `kubectl exec`
- [ ] `redis-0` pod is running with stable name
- [ ] PVC `redis-data-redis-0` exists and is Bound
- [ ] You can `redis-cli ping` and get `PONG`
- [ ] Data survives pod deletion (you proved this)
- [ ] DNS resolves `redis` to the pod IP
- [ ] You understand when to use Helm vs plain manifests

---

## Discovery Questions

1. Run `helm get manifest vault | grep "kind:" | sort | uniq -c | sort -rn`. How many different resource types did the Vault chart create? Pick two you haven't seen before and look them up with `kubectl explain <resource>`.

2. You wrote `clusterIP: None` on the Redis Service. What would change if you removed that line and let Kubernetes assign a ClusterIP? Would your app still be able to connect using the hostname `redis`? What's the practical difference?

3. The Redis StatefulSet has `volumeClaimTemplates`. What happens to the PVC if you `kubectl delete statefulset redis`? Does the data survive? Try it — delete the StatefulSet, check the PVC, recreate the StatefulSet, and see if Redis still has your data.

4. You deployed Redis with `redis:7-alpine`. Run `kubectl exec redis-0 -- redis-server --version` to see the exact version. How would you pin this to a specific patch version instead of floating on `7-alpine`? Why might you want to?

---

## Next Lab

Continue to [Lab 2: Wire Your App to Redis](../lab-02-configmaps-and-wiring/)
