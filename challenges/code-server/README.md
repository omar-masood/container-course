# Challenge: VS Code in the Browser on Kubernetes

**Time:** 45–60 minutes
**Objective:** Deploy a browser-accessible VS Code IDE to your kind cluster using hand-written manifests, persist your workspace with a PVC, and protect access with a Kubernetes Secret

**Prerequisites:** Weeks 04 and 05 completed (you should be comfortable with kind, kubectl, StatefulSets, PVCs, ConfigMaps, and Secrets)

---

## Why Code Server?

In the Minecraft challenge you deployed a game server using a Helm chart and a `values.yaml`. This time you're going the other direction — writing every manifest by hand. Same Kubernetes concepts, opposite workflow.

[code-server](https://github.com/coder/code-server) is VS Code running as a web server. You open a browser tab and get a full IDE — file explorer, terminal, extensions, the works — served from a pod in your cluster. The workspace lives on a PVC, so your files survive pod restarts. The password lives in a Secret, so it never touches your manifests in plaintext.

The "whoa" moment: you write code in a browser-based IDE, delete the pod, and your code is still there when it comes back.

```
┌────────────────────────────────────────────────────────┐
│                     kind cluster                        │
│                                                         │
│  ┌────────────────────────────────────────────────┐     │
│  │           StatefulSet: code-server-0            │     │
│  │                                                 │     │
│  │   ┌───────────────────────────────────────┐     │     │
│  │   │  codercom/code-server                  │     │     │
│  │   │                                        │     │     │
│  │   │  /home/coder ◄── PVC (workspace)       │     │     │
│  │   │  :8080       ◄── VS Code web UI        │     │     │
│  │   │                                        │     │     │
│  │   │  PASSWORD    ◄── Secret (login)        │     │     │
│  │   └───────────────────────────────────────┘     │     │
│  └────────────────────────────────────────────────┘     │
│                                                         │
│  ┌──────────────┐                                       │
│  │   Service     │                                       │
│  │   NodePort    │                                       │
│  │   :30080→8080 │                                       │
│  └──────────────┘                                       │
└────────────────────────────────────────────────────────┘

    Browser → localhost:8080 → NodePort 30080 → Pod :8080
```

---

## Part 1: Create Your kind Cluster

Create a cluster with a port mapping so the browser can reach code-server:

```bash
kind create cluster --name code-server --config starter/kind-config.yaml
```

Verify:

```bash
kubectl cluster-info --context kind-code-server
```

The kind config maps host port `8080` to node port `30080`. You'll configure the NodePort Service to match in Part 5.

---

## Part 2: Create the Namespace

Keep things isolated:

```bash
kubectl create namespace code-server
```

---

## Part 3: Write the Secret

code-server needs a password to protect access. Store it in a Kubernetes Secret.

> **Try scaffolding first.** Use `kubectl create secret` with `--dry-run=client -o yaml` to generate the YAML, then save it to a file. Don't just copy the solution.

```bash
kubectl create secret generic code-server-secret \
  --from-literal=PASSWORD=kubernetes-rocks \
  --namespace code-server \
  --dry-run=client -o yaml > secret.yaml
```

Apply it:

```bash
kubectl apply -f secret.yaml
```

Verify:

```bash
kubectl get secret code-server-secret -n code-server -o jsonpath='{.data.PASSWORD}' | base64 -d
```

You should see `kubernetes-rocks`. Remember — base64 is encoding, not encryption. Anyone with `kubectl get secret` access can read this.

---

## Part 4: Write the PVC

The workspace needs durable storage. Create a PVC that will be mounted at `/home/coder` — where code-server stores your files, settings, and extensions.

Create a file called `pvc.yaml`:

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: code-server-data
  namespace: code-server
  labels:
    app: code-server
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 2Gi
```

Walk through the fields:

- **`accessModes: ReadWriteOnce`** — One node can mount this volume for reading and writing. Fine for a single-replica workload.
- **`storage: 2Gi`** — Enough for a workspace. In kind, the `standard` StorageClass uses `local-path` provisioner — it allocates space on the node's filesystem.

Apply it:

```bash
kubectl apply -f pvc.yaml
```

Check that it's bound:

```bash
kubectl get pvc -n code-server
```

> **Why a standalone PVC instead of volumeClaimTemplates?** Either works. The Minecraft chart used `volumeClaimTemplates` inside the StatefulSet spec. Here you're creating the PVC separately and referencing it — this is the other pattern, and it gives you more control over the PVC lifecycle (it won't be auto-deleted if you delete the StatefulSet).

---

## Part 5: Write the StatefulSet

This is the main event. Create a file called `statefulset.yaml`:

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: code-server
  namespace: code-server
  labels:
    app: code-server
spec:
  serviceName: code-server
  replicas: 1
  selector:
    matchLabels:
      app: code-server
  template:
    metadata:
      labels:
        app: code-server
    spec:
      containers:
        - name: code-server
          image: codercom/code-server:latest
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: PASSWORD
              valueFrom:
                secretKeyRef:
                  name: code-server-secret
                  key: PASSWORD
          volumeMounts:
            - name: workspace
              mountPath: /home/coder
          resources:
            requests:
              memory: 512Mi
              cpu: 250m
            limits:
              memory: 1Gi
              cpu: 1000m
          readinessProbe:
            httpGet:
              path: /healthz
              port: http
            initialDelaySeconds: 5
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /healthz
              port: http
            initialDelaySeconds: 15
            periodSeconds: 30
      volumes:
        - name: workspace
          persistentVolumeClaim:
            claimName: code-server-data
```

Walk through the important parts:

- **`kind: StatefulSet`** — Stable pod identity (`code-server-0`), stable storage. Same reason you used a StatefulSet for Redis and Minecraft.
- **`serviceName: code-server`** — Required for StatefulSets. Points to the Service that governs DNS for the pods.
- **`secretKeyRef`** — Pulls the `PASSWORD` value from the Secret you created. The container sees it as a plain environment variable, but the value never appears in this manifest.
- **`volumeMounts` + `volumes`** — Mounts the PVC at `/home/coder`. Everything you create in VS Code lives here.
- **`resources`** — VS Code is a real IDE and will use real resources. The limits prevent it from starving other workloads on the node.
- **`readinessProbe` / `livenessProbe`** — code-server exposes `/healthz`. Kubernetes uses these to know when the pod is ready for traffic and when it needs a restart.

Apply it:

```bash
kubectl apply -f statefulset.yaml
```

Watch the pod come up:

```bash
kubectl get pods -n code-server -w
```

It should reach `1/1 Ready` within 30–60 seconds.

---

## Part 6: Write the Service

Expose code-server with a NodePort Service so your browser can reach it:

Create a file called `service.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: code-server
  namespace: code-server
  labels:
    app: code-server
spec:
  type: NodePort
  selector:
    app: code-server
  ports:
    - name: http
      port: 8080
      targetPort: 8080
      nodePort: 30080
```

Walk through the fields:

- **`type: NodePort`** — Exposes the Service on a static port on every node. In kind, the node is a Docker container, and the kind config maps host port 8080 to node port 30080.
- **`nodePort: 30080`** — The specific port on the node. Must be in the 30000–32767 range. This matches the kind config's `containerPort`.
- **`selector: app: code-server`** — Routes traffic to pods with this label.

Apply it:

```bash
kubectl apply -f service.yaml
```

---

## Part 7: Open VS Code in Your Browser

Navigate to:

```
http://localhost:8080
```

You should see a login screen. Enter the password from your Secret (`kubernetes-rocks`).

You're now running VS Code inside a Kubernetes pod, accessed through a NodePort Service, with your workspace stored on a PVC.

**Do some work to prove it:**

1. Open the integrated terminal (`` Ctrl+`  ``)
2. Create a file:
   ```bash
   echo "Hello from Kubernetes!" > /home/coder/hello.txt
   mkdir -p /home/coder/my-project
   echo "print('deployed on k8s')" > /home/coder/my-project/app.py
   ```
3. Open `my-project/app.py` in the editor — make some changes, save them
4. Install an extension (like a theme or language pack) — these are stored in the workspace too

---

## Part 8: Prove Persistence

Delete the pod:

```bash
kubectl delete pod -n code-server code-server-0
```

Watch it come back:

```bash
kubectl get pods -n code-server -w
```

Once it's `1/1 Ready`, refresh your browser at `http://localhost:8080`. Log in again.

Your files are still there. Your extensions are still installed. Your settings are intact. The PVC held everything while the pod was gone.

> **The pattern is identical to Minecraft and Redis.** StatefulSet noticed 0/1 pods, created `code-server-0` with the same identity, and the PVC reattached at `/home/coder`. The only difference is what's running inside the container.

---

## Part 9: Inspect What You Built

Review all the resources in your namespace:

```bash
kubectl get all,pvc,secret -n code-server
```

You should see:
- **StatefulSet** `code-server` with 1/1 ready
- **Pod** `code-server-0` (stable name from StatefulSet)
- **Service** `code-server` (NodePort 30080)
- **PVC** `code-server-data` (Bound)
- **Secret** `code-server-secret`

Compare this to the Minecraft challenge. The Helm chart generated these same resource types from a `values.yaml`. Here you wrote each one yourself. Neither approach is "better" — they're tools for different situations (Week 05 lesson).

---

## Part 10: Clean Up

```bash
kubectl delete namespace code-server
kind delete cluster --name code-server
```

Deleting the namespace removes everything inside it — the StatefulSet, Pod, Service, Secret, and PVC.

---

## Checkpoint

- [ ] You wrote all four manifests by hand (Secret, PVC, StatefulSet, Service)
- [ ] VS Code loaded in your browser at `localhost:8080`
- [ ] You logged in with the password from your Kubernetes Secret
- [ ] You created files and installed extensions in the IDE
- [ ] Files and extensions survived pod deletion
- [ ] You can explain why the PVC is mounted at `/home/coder` specifically
- [ ] You can explain the difference between this approach (hand-written manifests) and the Minecraft approach (Helm chart)

---

## Discovery Questions

1. You used a standalone PVC and referenced it in the StatefulSet's `volumes` section. The Minecraft chart used `volumeClaimTemplates` instead. What's the practical difference? What happens to each type of PVC when you delete the StatefulSet?

2. The password is passed as an environment variable via `secretKeyRef`. What's another way to mount a Secret into a container? (Hint: `volumeMounts` works for Secrets too.) When would you prefer one over the other?

3. Run `kubectl describe pod code-server-0 -n code-server` and find the `Events` section. Trace the lifecycle: Scheduled → Pulling → Pulled → Created → Started. Which Kubernetes component is responsible for each step?

4. What would happen if you changed `replicas: 2` on this StatefulSet? Would you get two separate VS Code instances? Would they share the PVC? Try it and find out what error you get. (Hint: `ReadWriteOnce`.)

5. You used `codercom/code-server:latest` for the image tag. Why is `:latest` considered bad practice in production? What would you use instead? (Hint: check the [code-server releases](https://github.com/coder/code-server/releases) for a pinned version.)

---

## Stretch Goal: Add a ConfigMap for Settings

code-server reads settings from `~/.local/share/code-server/User/settings.json`. Create a ConfigMap with your preferred VS Code settings and mount it into the container:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: code-server-settings
  namespace: code-server
data:
  settings.json: |
    {
      "editor.fontSize": 16,
      "editor.tabSize": 2,
      "workbench.colorTheme": "Default Dark Modern",
      "terminal.integrated.defaultProfile.linux": "bash",
      "editor.minimap.enabled": false
    }
```

Mount it as a file in the StatefulSet:

```yaml
volumeMounts:
  - name: settings
    mountPath: /home/coder/.local/share/code-server/User/settings.json
    subPath: settings.json
```

Now your IDE preferences are version-controlled Kubernetes configuration, not manual clicks in a UI. That's infrastructure as code.

---

## Resources

- [code-server (GitHub)](https://github.com/coder/code-server)
- [code-server Docker image](https://hub.docker.com/r/codercom/code-server)
- [Kubernetes StatefulSets](https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/)
- [Kubernetes Secrets](https://kubernetes.io/docs/concepts/configuration/secret/)
- [Kubernetes Persistent Volumes](https://kubernetes.io/docs/concepts/storage/persistent-volumes/)
