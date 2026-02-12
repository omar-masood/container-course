# Challenge: Minecraft Server on Kubernetes

**Time:** 45–60 minutes
**Objective:** Deploy a persistent Minecraft server to your kind cluster using Helm, prove that world data survives pod deletion, and lock down the admin console with a Kubernetes Secret

**Prerequisites:** Weeks 04 and 05 completed (you should be comfortable with kind, kubectl, Helm, StatefulSets, PVCs, ConfigMaps, and Secrets)

---

## Why Minecraft?

Redis was a fine first StatefulSet — but it's hard to _feel_ persistence when all you're storing is a counter. A Minecraft server is the same problem made visceral: you build a house, the pod dies, and either your house is there when it comes back or it isn't. That's the entire point of a PVC.

The `itzg/minecraft-server` Helm chart wraps the popular [`itzg/minecraft-server`](https://hub.docker.com/r/itzg/minecraft-server/) Docker image. It gives you a fully configurable Minecraft server controlled entirely through a `values.yaml` — game mode, difficulty, MOTD, resource limits, persistence, RCON — all the things you've been learning about, pointed at something you can actually log into.

```
┌──────────────────────────────────────────────────────┐
│                    kind cluster                       │
│                                                      │
│  ┌──────────────────────────────────────────────┐    │
│  │          StatefulSet: minecraft-0             │    │
│  │                                               │    │
│  │   ┌─────────────────────────────────────┐     │    │
│  │   │  itzg/minecraft-server               │     │    │
│  │   │                                      │     │    │
│  │   │  /data  ◄── PVC (world saves)        │     │    │
│  │   │  :25565 ◄── game traffic (NodePort)  │     │    │
│  │   │  :25575 ◄── RCON admin (ClusterIP)   │     │    │
│  │   └─────────────────────────────────────┘     │    │
│  └──────────────────────────────────────────────┘    │
│                                                      │
│  ┌────────────┐    ┌────────────┐                    │
│  │  Service    │    │  Service   │                    │
│  │  NodePort   │    │  ClusterIP │                    │
│  │  :25565     │    │  :25575    │                    │
│  │  (game)     │    │  (rcon)    │                    │
│  └────────────┘    └────────────┘                    │
└──────────────────────────────────────────────────────┘
```

---

## Part 1: Add the Helm Repo

Add the itzg chart repository and inspect what's available.

```bash
helm repo add itzg https://itzg.github.io/minecraft-server-charts/
helm repo update
```

Search the repo to see the chart:

```bash
helm search repo itzg
```

You should see `itzg/minecraft` in the results. Now look at what the chart can do:

```bash
helm show values itzg/minecraft | head -100
```

That's a lot of options. You don't need most of them. The values file in `starter/` has the ones that matter.

---

## Part 2: Understand the Values File

Open `starter/minecraft-values.yaml` and read through it. Every field maps to a Kubernetes concept you've already learned:

```bash
cat starter/minecraft-values.yaml
```

Walk through the key sections:

- **`workloadAsStatefulSet: true`** — Tells the chart to create a StatefulSet instead of a Deployment. Minecraft needs stable identity and stable storage — exactly what StatefulSets provide. Same reason you used a StatefulSet for Redis.

- **`persistence.dataDir.enabled: true`** — Creates a PVC mounted at `/data` inside the container. This is where world saves, player data, and server configuration live. Without this, `emptyDir` is used and everything vanishes when the pod dies.

- **`resources`** — Minecraft is memory-hungry. The JVM heap (`minecraftServer.memory`) is set to `1G`, and the container limit is set to `1536Mi` — the extra headroom covers JVM overhead outside the heap. The CPU request is `500m` with a limit of `1000m`.

- **`minecraftServer.rcon`** — RCON (Remote Console) lets you run server commands without joining the game. The password is stored in a Kubernetes Secret created by the chart. You'll use this to interact with the server from `kubectl exec`.

- **`minecraftServer.serviceType: NodePort`** — Exposes port 25565 on the kind node so you can connect with a Minecraft client from your machine. This is the same concept as NodePort from Week 06, but for TCP game traffic instead of HTTP.

> **This should feel familiar.** A StatefulSet with a PVC, a Secret for credentials, a ConfigMap-driven configuration, and a Service to expose it — this is the same pattern as your Redis deployment, just pointed at a game server.

---

## Part 3: Create Your kind Cluster

You need a kind cluster with a port mapping for the Minecraft game port. Create it with the provided config:

```bash
kind create cluster --name minecraft --config starter/kind-config.yaml
```

Verify the cluster is running:

```bash
kubectl cluster-info --context kind-minecraft
kubectl get nodes
```

---

## Part 4: Deploy the Server

Install the chart with your values file:

```bash
helm install minecraft itzg/minecraft \
  -f starter/minecraft-values.yaml \
  --namespace minecraft \
  --create-namespace
```

Breaking this down:
- `helm install` — install a release
- `minecraft` — the release name (you choose this)
- `itzg/minecraft` — the chart from the repo you added
- `-f starter/minecraft-values.yaml` — your configuration overrides
- `--namespace minecraft --create-namespace` — deploy into a dedicated namespace

Watch the pod come up:

```bash
kubectl get pods -n minecraft -w
```

Minecraft takes a while to start — it downloads the server jar, generates the world, and runs startup tasks. The pod will show `0/1 Running` for a minute or two before the readiness probe passes and it becomes `1/1 Ready`.

> **Be patient.** First boot can take 2–3 minutes depending on your machine. The chart uses `mc-health` as a readiness probe, which checks that the server is fully initialized and accepting connections.

While you wait, inspect what Helm created:

```bash
kubectl get all -n minecraft
kubectl get pvc -n minecraft
kubectl get secrets -n minecraft
```

You should see:
- A **StatefulSet** (not a Deployment) named `minecraft-minecraft`
- A **Pod** named `minecraft-minecraft-0` (stable identity from the StatefulSet)
- Two **Services** — one for game traffic (NodePort), one for RCON (ClusterIP)
- A **PVC** bound to a PersistentVolume
- A **Secret** containing the RCON password

---

## Part 5: Connect and Interact

### Option A: Minecraft Client (if you have one)

If you have Minecraft Java Edition installed, connect to:

```
localhost:25565
```

You should see the MOTD from your values file and be able to join the world.

### Option B: RCON (no client needed)

You don't need a Minecraft client to verify the server works. Use RCON to interact from the command line. First, exec into the pod:

```bash
kubectl exec -it -n minecraft minecraft-minecraft-0 -- rcon-cli
```

This drops you into the RCON console. Try some commands:

```
/list
/seed
/time set day
/say Hello from Kubernetes!
```

Type `/list` to confirm the server is running and accepting commands. Type `exit` to leave RCON.

### Verify the World Exists

Check that world data is being written to the PVC:

```bash
kubectl exec -n minecraft minecraft-minecraft-0 -- ls /data/world
```

You should see directories like `region/`, `playerdata/`, `level.dat` — this is the Minecraft world living on your PVC.

---

## Part 6: Prove Persistence

This is the whole point. Delete the pod and verify the world survives.

First, note the world seed:

```bash
kubectl exec -n minecraft minecraft-minecraft-0 -- rcon-cli /seed
```

Write it down. Now kill the pod:

```bash
kubectl delete pod -n minecraft minecraft-minecraft-0
```

Watch the StatefulSet controller bring it back:

```bash
kubectl get pods -n minecraft -w
```

The new pod will be named `minecraft-minecraft-0` again — same name, same PVC reattached. Once it's `1/1 Ready`, check the seed:

```bash
kubectl exec -n minecraft minecraft-minecraft-0 -- rcon-cli /seed
```

Same seed. Same world. The PVC held your data while the pod was gone.

> **This is the reconciliation loop + persistent storage working together.** The StatefulSet controller noticed the desired state (1 pod) didn't match actual state (0 pods), created a replacement with the same identity, and the PVC reattached automatically. If you had used a Deployment with `emptyDir`, the world would be gone.

---

## Part 7: Inspect the Chart's Resources

Now that you've seen it work, look at what the Helm chart actually generated:

```bash
helm get manifest minecraft -n minecraft
```

Scroll through the output. You'll recognize every resource type:
- **Secret** — RCON password (base64 encoded, just like Week 05)
- **Service (NodePort)** — game traffic on 25565
- **Service (ClusterIP)** — RCON on 25575
- **StatefulSet** — with `volumeClaimTemplates`, readiness/liveness probes, env vars, resource limits

Compare this to the Redis manifests you wrote by hand in Week 05. The Helm chart is generating the same kinds of resources — it's just templating them from your values file.

> **Try this.** Run `helm template minecraft itzg/minecraft -f starter/minecraft-values.yaml -n minecraft` to see the rendered manifests without installing. Compare the StatefulSet spec to the one you wrote for Redis.

---

## Part 8: Clean Up

When you're done:

```bash
helm uninstall minecraft -n minecraft
kubectl delete namespace minecraft
kind delete cluster --name minecraft
```

Note that `helm uninstall` does **not** delete PVCs by default — this is a safety feature to prevent accidental data loss. In a real cluster you'd need to clean those up separately.

---

## Checkpoint

- [ ] `helm list -n minecraft` showed the `minecraft` release
- [ ] `kubectl get statefulset -n minecraft` showed a StatefulSet (not a Deployment)
- [ ] `kubectl get pvc -n minecraft` showed a bound PersistentVolumeClaim
- [ ] You interacted with the server via RCON or a Minecraft client
- [ ] World data survived pod deletion (same seed, same world)
- [ ] You can explain why this is a StatefulSet and not a Deployment

---

## Discovery Questions

1. Run `kubectl describe pvc -n minecraft` and look at the `StorageClass`. What provisioner is kind using? What would change in a cloud cluster (EKS, AKS, GKE)?

2. The chart creates two Services — one NodePort for game traffic, one ClusterIP for RCON. Why is RCON kept as ClusterIP? What would be the security implication of exposing it as a NodePort?

3. What happens if you set `persistence.dataDir.enabled: false` and delete the pod? Try it and see.

4. Run `helm get values minecraft -n minecraft` vs `helm get values minecraft -n minecraft --all`. What's the difference? Where do the default values come from?

5. The `minecraftServer.memory` field controls JVM heap (`-Xmx`), but the container `resources.limits.memory` is set higher. What happens if the JVM heap equals the container memory limit? (Hint: OOMKilled.)

---

## Stretch Goal: Two Servers, Two Modes

Deploy a second Minecraft server in the same cluster with a different game mode:

```bash
cp starter/minecraft-values.yaml creative-values.yaml
```

Edit `creative-values.yaml`:
- Change `gameMode` to `creative`
- Change `motd` to something different
- Change the NodePort to `30566` (so it doesn't collide)
- Change `difficulty` to `peaceful`

Install a second release:

```bash
helm install minecraft-creative itzg/minecraft \
  -f creative-values.yaml \
  --namespace minecraft-creative \
  --create-namespace
```

Now you have two independent Minecraft servers, each with their own StatefulSet, PVC, and Service — isolated by namespace. This is the same pattern as your dev/prod environments, just with game servers instead of Flask apps.

---

## Resources

- [itzg/minecraft-server-charts (GitHub)](https://github.com/itzg/minecraft-server-charts)
- [itzg/minecraft-server (Docker Hub)](https://hub.docker.com/r/itzg/minecraft-server/)
- [Kubernetes StatefulSets](https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/)
- [Kubernetes Persistent Volumes](https://kubernetes.io/docs/concepts/storage/persistent-volumes/)
- [Helm Documentation](https://helm.sh/docs/)
