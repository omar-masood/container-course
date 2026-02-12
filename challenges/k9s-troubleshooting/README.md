# Challenge: Troubleshooting with k9s

**Time:** 45–60 minutes
**Objective:** Learn to use k9s — a terminal UI for Kubernetes — to diagnose and fix six broken workloads that Jerry deployed before going on vacation

**Prerequisites:** Week 04 completed (you should be comfortable with kubectl, Pods, Deployments, and Services)

---

## Why k9s?

`kubectl` is the foundation. You'll always need it. But when you're staring at a cluster with dozens of pods in various states of failure, typing `kubectl get pods`, then `kubectl describe pod <name>`, then `kubectl logs <name>`, then repeating that for the next pod... it gets old fast.

[k9s](https://k9scli.io/) is a terminal UI that gives you a real-time, navigable view of your cluster. Think of it as `htop` for Kubernetes. You can watch pods come and go, tail logs, shell into containers, edit resources live, and drill into problems — all without leaving a single terminal window.

```
┌──────────────────────────────────────────────────────────────┐
│ k9s                                                          │
│                                                              │
│  NAMESPACE   NAME              READY  STATUS             AGE │
│  jerry       website-7f4b8...  0/1    ImagePullBackOff   2m  │
│  jerry       worker-9c2d1...   0/1    CreateContainer... 2m  │
│  jerry       api-5d8f2...      1/1    Running            2m  │
│  jerry       api-8a3e1...      1/1    Running            2m  │
│  jerry       api-b7c94...      1/1    Running            2m  │
│  jerry       hungry-app-...    0/1    Pending            2m  │
│  jerry       backend-6e...     0/1    CreateContainer... 2m  │
│  jerry       logger-4a...      0/1    CrashLoopBackOff   2m  │
│                                                              │
│  <d>escribe  <l>ogs  <s>hell  <y>aml  <e>dit  <ctrl-d>elete │
└──────────────────────────────────────────────────────────────┘
```

This challenge puts you in front of a broken cluster and teaches you to use k9s to find and fix every problem.

---

## Part 1: Install k9s

### macOS

```bash
brew install derailed/k9s/k9s
```

### Linux

```bash
# Download the latest release
curl -sL https://github.com/derailed/k9s/releases/latest/download/k9s_Linux_amd64.tar.gz | tar xz -C /tmp
sudo mv /tmp/k9s /usr/local/bin/
```

### Windows (WSL)

```bash
curl -sL https://github.com/derailed/k9s/releases/latest/download/k9s_Linux_amd64.tar.gz | tar xz -C /tmp
sudo mv /tmp/k9s /usr/local/bin/
```

Verify it's installed:

```bash
k9s version
```

---

## Part 2: Deploy the Broken Cluster

Create a kind cluster and deploy Jerry's workloads:

```bash
kind create cluster --name k9s-lab --config starter/kind-config.yaml
```

Create the namespace and deploy the broken workloads:

```bash
kubectl create namespace jerry
kubectl apply -f starter/broken-workloads.yaml
```

> **Do not read `broken-workloads.yaml` before attempting the challenge.** The entire point is to diagnose problems using k9s, not by reading the source. In the real world, the person who wrote the manifests is on vacation and you're the one holding the pager.

---

## Part 3: Launch k9s

```bash
k9s --namespace jerry
```

You should see a pod view with several unhealthy workloads. Welcome to Jerry's mess.

### Essential Navigation

Before you start fixing things, learn to move around. k9s is keyboard-driven — no mouse.

| Key | Action |
|-----|--------|
| `:` | **Command mode** — type a resource (`:pod`, `:deploy`, `:svc`, `:events`, `:ns`) |
| `/` | **Filter** — search/filter the current view |
| `Enter` | Drill into the selected resource |
| `Esc` | Go back / cancel |
| `d` | **Describe** — same as `kubectl describe` |
| `l` | **Logs** — tail container logs in real time |
| `s` | **Shell** — exec into the container |
| `y` | **YAML** — view the raw manifest |
| `e` | **Edit** — live-edit the resource (like `kubectl edit`) |
| `Ctrl+d` | **Delete** — delete the selected resource |
| `?` | **Help** — show all keybindings |
| `Ctrl+c` | **Quit** k9s |

Try these now:

1. Press `:` and type `pod` then Enter — you're in the pod view
2. Use arrow keys to select a pod, press `d` to describe it
3. Press `Esc` to go back to the pod list
4. Press `:` and type `events` then Enter — see cluster events
5. Press `:` and type `deploy` then Enter — see deployments

> **k9s refreshes in real-time.** You don't need to re-run commands to see updates. Fix something in another terminal and watch k9s update instantly.

---

## Part 4: The Scenarios

There are six broken workloads in the `jerry` namespace. For each one, use k9s to:

1. **Identify** the problem (what status is the pod in?)
2. **Diagnose** the root cause (describe, logs, events, YAML)
3. **Fix** it (edit the resource, apply a fix, or create a missing dependency)
4. **Verify** the pod reaches `Running` / `1/1 Ready`

Work through them in any order. Each scenario teaches a different k9s skill.

---

### Scenario 1: `website`

**Symptom:** Pods are not running.

**k9s skills to practice:**
- Select the pod and press `d` (describe)
- Look at the **Events** section at the bottom
- Press `:` → `events` to see cluster-wide events filtered to this pod

**Guiding questions:**
- What does the pod status tell you?
- What image is it trying to pull?
- Does that image tag actually exist?

**How to fix:** Use `e` on the Deployment (`:deploy` → select `website` → `e`) to edit the image tag to a valid one. Save and exit the editor.

<details>
<summary>Hint</summary>

The image tag `nginx:v999` doesn't exist. Change it to `nginx:1.27` or `nginx:latest`.

In k9s: `:deploy` → select `website` → `e` → find the `image:` line → change `nginx:v999` to `nginx:1.27` → save and quit (`:wq`).

</details>

---

### Scenario 2: `worker`

**Symptom:** Pod can't start.

**k9s skills to practice:**
- Press `d` on the pod — read the Events section carefully
- Press `:` → `configmap` (or `:cm`) to see what ConfigMaps exist in the namespace
- Press `y` to view YAML of the pod and find what it's looking for

**Guiding questions:**
- What volume is the pod trying to mount?
- Does that ConfigMap exist?
- What should the ConfigMap contain?

**How to fix:** Create the missing ConfigMap that the pod expects.

<details>
<summary>Hint</summary>

The pod mounts a ConfigMap called `worker-config` at `/config`, and the container tries to `cat /config/app.conf`. Create the ConfigMap:

```bash
kubectl create configmap worker-config \
  --from-literal=app.conf="mode=production" \
  -n jerry
```

The pod should start automatically once the ConfigMap exists.

</details>

---

### Scenario 3: `api`

**Symptom:** The pods are actually Running — but the Service isn't working.

**k9s skills to practice:**
- Press `:` → `svc` to view Services
- Select the `api` Service and press `d` (describe)
- Look at the **Endpoints** field — is it empty?
- Press `:` → `ep` (Endpoints) to confirm
- Compare the Service selector to the pod labels

**Guiding questions:**
- What selector is the Service using?
- What labels do the api pods actually have?
- Why are there zero Endpoints?

**How to fix:** Edit the Service selector to match the actual pod labels.

<details>
<summary>Hint</summary>

The Service selector is `app: api-server` but the pods have `app: api`. Edit the Service:

In k9s: `:svc` → select `api` → `e` → change `api-server` to `api` → save.

Or with kubectl:
```bash
kubectl patch svc api -n jerry -p '{"spec":{"selector":{"app":"api"}}}'
```

After fixing, `:ep` should show 3 endpoints (one per api pod).

</details>

---

### Scenario 4: `hungry-app`

**Symptom:** Pod is stuck and never starts.

**k9s skills to practice:**
- Press `d` on the pod — read the **Conditions** and **Events** sections
- Press `:` → `node` to see node resources
- Select a node and press `d` — look at **Allocatable** vs **Allocated resources**
- Press `:` → `events` and filter with `/hungry` to see scheduler messages

**Guiding questions:**
- What's the pod requesting?
- How much memory do the nodes actually have?
- What does the scheduler event say?

**How to fix:** Edit the Deployment to request a realistic amount of memory.

<details>
<summary>Hint</summary>

The pod requests `64Gi` of memory — far more than any node has. Change it to `64Mi`:

In k9s: `:deploy` → select `hungry-app` → `e` → change `64Gi` to `64Mi` (both requests and limits) → save.

</details>

---

### Scenario 5: `backend`

**Symptom:** Pod can't start.

**k9s skills to practice:**
- Press `d` on the pod — look for the specific error in Events
- Press `:` → `secret` (or `:sec`) to check what Secrets exist
- Press `y` on the pod to find the Secret reference

**Guiding questions:**
- What Secret is the pod referencing?
- Does that Secret exist?
- What key does the pod expect inside the Secret?

**How to fix:** Create the missing Secret.

<details>
<summary>Hint</summary>

The pod references a Secret called `db-credentials` with key `password`. Create it:

```bash
kubectl create secret generic db-credentials \
  --from-literal=password=supersecret \
  -n jerry
```

</details>

---

### Scenario 6: `logger`

**Symptom:** Pod keeps restarting.

**k9s skills to practice:**
- Press `l` on the pod to tail the logs — what's the last thing it printed?
- Press `p` while viewing logs to see **previous** container logs (the container that crashed)
- Press `d` on the pod — look at **Restart Count**
- Press `:` → `events` and filter with `/logger`

**Guiding questions:**
- What is the container trying to do?
- Why does it exit?
- Is this a Kubernetes problem or an application problem?
- What would you tell the developer?

**How to fix:** This one is intentionally ambiguous. The container tries to connect to a Postgres database that doesn't exist. There are two valid responses:

1. **Deploy a Postgres database** (the infrastructure fix)
2. **Make the app handle the missing database gracefully** (the application fix)

For this challenge, the simplest fix is to make the container succeed by updating the command to not exit on failure.

<details>
<summary>Hint</summary>

The container exits with code 1 because the database doesn't exist. The simplest fix: edit the Deployment and change the command so it doesn't `exit 1`.

In k9s: `:deploy` → select `logger` → `e` → remove the `exit 1` line and replace it with `sleep 3600` → save.

Or, if you want the "real" fix, deploy a Postgres instance. But for this challenge, recognizing that the problem is application-level (not Kubernetes-level) is the key lesson.

</details>

---

## Part 5: Power Features

Now that you've fixed everything, explore these advanced k9s features:

### Pulse View

```
:pulse
```

Shows a cluster health dashboard — node status, pod counts, and resource utilization at a glance. This is the first thing to check when you inherit an unfamiliar cluster.

### Xray View

```
:xray deploy jerry
```

Shows a tree view of Deployments → ReplicaSets → Pods in the `jerry` namespace. Helps you understand the ownership chain — which Deployment owns which pods.

### Sort by Status

In the pod view, press `Shift+S` to sort by status. All the unhealthy pods float to the top. In a namespace with 100 pods, this finds problems instantly.

### Filter by Label

Press `/` and type `app=api` to filter pods by label. Press `Esc` to clear the filter. This is faster than `kubectl get pods -l app=api`.

### Port Forward

Select a running pod and press `Shift+F` to set up a port-forward directly from k9s. No need to switch terminals.

### Resource YAML Diff

When you edit a resource with `e` and save, k9s applies the change immediately — the same as `kubectl apply`. Watch the pod list update in real time after your edit.

---

## Part 6: Clean Up

```bash
kind delete cluster --name k9s-lab
```

---

## Checkpoint

- [ ] k9s is installed and you can launch it with `k9s`
- [ ] You fixed `website` — bad image tag (ImagePullBackOff)
- [ ] You fixed `worker` — missing ConfigMap (CreateContainerConfigError)
- [ ] You fixed `api` — Service selector mismatch (no Endpoints)
- [ ] You fixed `hungry-app` — impossible resource request (Pending)
- [ ] You fixed `backend` — missing Secret (CreateContainerConfigError)
- [ ] You fixed `logger` — application crash (CrashLoopBackOff)
- [ ] All six workloads show `1/1 Running`
- [ ] You can navigate k9s without a cheat sheet: `:resource`, `d`, `l`, `s`, `y`, `e`, `/`

---

## Discovery Questions

1. What's the difference between pressing `l` (logs) on a running pod vs a CrashLoopBackOff pod? How do you see the previous container's logs in k9s?

2. In scenario 3, the pods were `Running` but the Service had no Endpoints. How would you have caught this with only `kubectl` commands? How many commands would it take vs. k9s?

3. In scenario 4, the scheduler couldn't place the pod. Press `:` → `node` → select a node → `d`. Find the **Allocated resources** section. How much of the node's memory is already committed? What happens if all pods on a node exceed their memory limits simultaneously?

4. k9s has a `:popeye` command (if the popeye plugin is installed) that scans your cluster for misconfigurations. How does an automated scanner compare to manual troubleshooting? What would it catch that you might miss? What would it miss that you'd catch?

5. You used `e` (edit) in k9s to fix resources live. In a production GitOps workflow (like your ArgoCD setup), why would this be a bad idea? What would ArgoCD do to your live edit?

---

## k9s Quick Reference Card

Keep this handy until the keybindings are muscle memory.

```
NAVIGATION                           ACTIONS
─────────────────────────────────    ─────────────────────────────
:pod     switch to pods view         d    describe
:deploy  switch to deployments       l    logs (p = previous)
:svc     switch to services          s    shell into container
:sec     switch to secrets           y    view YAML
:cm      switch to configmaps        e    edit resource live
:ns      switch to namespaces        Ctrl+d  delete resource
:node    switch to nodes             Shift+f port-forward
:events  switch to events
:xray    resource dependency tree    FILTERING
:pulse   cluster health dashboard    /    filter current view
                                     Esc  clear filter / go back
?        help (all keybindings)
Ctrl+c   quit k9s                    SORTING
                                     Shift+S  sort by status
                                     Shift+A  sort by age
```

---

## Resources

- [k9s Official Site](https://k9scli.io/)
- [k9s GitHub](https://github.com/derailed/k9s)
- [k9s Keybindings Reference](https://k9scli.io/topics/commands/)
- [Kubernetes Debugging Guide](https://kubernetes.io/docs/tasks/debug/)
