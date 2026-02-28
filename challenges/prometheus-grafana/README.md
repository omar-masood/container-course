# Challenge: Observability Stack with Prometheus & Grafana

**Time:** 60–90 minutes
**Objective:** Deploy the kube-prometheus-stack via Helm, explore what it installs, access the Grafana dashboard, and customize it with something that's yours

**Prerequisites:** Weeks 04 and 05 completed (kind, kubectl, Helm, Deployments, Services). `helm install` should feel familiar.

---

## Why Observability?

Every production Kubernetes cluster runs some version of this stack. You can deploy a perfect application — right image, right resources, right probes — and still have no idea what it's actually doing once it's running. Observability answers the questions `kubectl get pods` can't: Is my app slow? Is it using more memory over time? Did it spike CPU at 3am?

[Prometheus](https://prometheus.io/) scrapes metrics from your cluster and workloads on a timer and stores them as time-series data. [Grafana](https://grafana.com/) turns those metrics into dashboards you can read at a glance. The [kube-prometheus-stack](https://github.com/prometheus-community/helm-charts/tree/main/charts/kube-prometheus-stack) Helm chart installs both — wired together, with a full set of pre-built Kubernetes dashboards included.

```
┌─────────────────────────────────────────────────────────────────┐
│                         kind cluster                             │
│                                                                  │
│  ┌──────────────┐   scrapes metrics    ┌────────────────────┐   │
│  │  your pods   │ ◄─────────────────── │  Prometheus        │   │
│  │  kube-state  │                      │  (stores TSDB)     │   │
│  │  node-export │                      └────────┬───────────┘   │
│  └──────────────┘                               │               │
│                                                 │ queries        │
│                                                 ▼               │
│                                      ┌────────────────────┐     │
│                                      │  Grafana           │     │
│                                      │  (dashboards + UI) │     │
│                                      └────────┬───────────┘     │
└───────────────────────────────────────────────┼─────────────────┘
                                                │ NodePort :30300
                                                ▼
                                      http://localhost:3000
```

The "whoa" moment: you deploy this stack and immediately get dashboards showing CPU, memory, pod restarts, and network traffic across your entire cluster — without writing a single line of instrumentation code.

---

## Part 1: Create Your kind Cluster

```bash
kind create cluster --name observability --config starter/kind-config.yaml
kubectl cluster-info --context kind-observability
```

The kind config maps host port `3000` to node port `30300` — your browser reaches Grafana directly without a port-forward.

---

## Part 2: Add the Helm Repo

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
```

Browse what's available:

```bash
helm search repo prometheus-community
```

The chart you want is `prometheus-community/kube-prometheus-stack`. Before installing, skim the default values:

```bash
helm show values prometheus-community/kube-prometheus-stack | less
```

That's a lot of configuration surface. The `starter/monitoring-values.yaml` cuts it down to what matters for a local kind cluster. Read through it before moving on — understand what each section is doing.

---

## Part 3: Install the Stack

```bash
helm install monitoring prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --create-namespace \
  -f starter/monitoring-values.yaml \
  --wait
```

This takes 2–3 minutes. Open a second terminal and watch:

```bash
kubectl get pods -n monitoring -w
```

When settled you should see pods for Grafana, Prometheus, the Prometheus Operator, kube-state-metrics, and node-exporter — five separate components, all wired together, from one `helm install`.

Explore what the chart created:

```bash
# Count resource kinds
helm get manifest monitoring -n monitoring | grep "^kind:" | sort | uniq -c | sort -rn

# How many CRDs did the chart install?
kubectl get crd | grep coreos
```

---

## Part 4: Access Grafana

Open `http://localhost:3000` in your browser.

Log in with:
- **Username:** `admin`
- **Password:** `grafana-k8s-lab`

### Tour the pre-built dashboards

Click **Dashboards** in the left sidebar. Open the "Kubernetes" folder and explore:

- **Kubernetes / Compute Resources / Cluster** — CPU and memory across all nodes
- **Kubernetes / Compute Resources / Namespace (Pods)** — per-pod breakdown
- **Kubernetes / Networking / Cluster** — network I/O
- **Node Exporter / Nodes** — host-level metrics: CPU, disk, memory

None of this required any configuration from you. The chart pre-wired Prometheus to scrape the right targets and pre-loaded these dashboards on install.

---

## Part 5: Explore Prometheus

```bash
kubectl port-forward service/monitoring-kube-prometheus-prometheus -n monitoring 9090:9090 &
```

Open `http://localhost:9090` and try some PromQL queries:

```promql
# All running pods in the cluster
kube_pod_status_phase{phase="Running"}

# CPU usage rate per container over 5 minutes
rate(container_cpu_usage_seconds_total[5m])

# Memory working set per container
container_memory_working_set_bytes{container!=""}
```

Then click **Status → Targets**. Every green row is a scrape endpoint actively feeding metrics into Prometheus. Find the node-exporter and kube-state-metrics targets and understand what each contributes.

---

## Part 6: Deploy a Workload to Watch

```bash
kubectl create namespace demo
kubectl create deployment demo-app \
  --image=nginx:1.27 \
  --replicas=3 \
  -n demo
kubectl expose deployment demo-app --port=80 --type=ClusterIP -n demo
```

Once pods are running, go to Grafana → **Kubernetes / Compute Resources / Namespace (Pods)** and switch the namespace dropdown to `demo`. Your pods appear with live metrics.

Generate traffic so the graphs move:

```bash
kubectl run load-gen \
  --image=busybox:1.36 \
  --restart=Never \
  -n demo \
  -- sh -c "while true; do wget -q -O- http://demo-app.demo.svc.cluster.local/ > /dev/null; sleep 0.1; done"
```

Watch the network I/O panels react in Grafana.

---

## Part 7: Make It Yours

Pick **one** extension. This is what makes your repo worth showing someone:

**Option A — Custom Grafana Dashboard**
Build a new dashboard from scratch (+ → Dashboard → Add visualization). Create at least two panels showing something specific to your `demo-app` — request rate, memory over time, pod restart count. Export the dashboard JSON (Share → Export → Save to file) and commit it to your repo with a README section explaining each panel and how to import it.

**Option B — Custom values.yaml**
Extend `monitoring-values.yaml` to enable something disabled by default. Ideas: enable Alertmanager and configure a webhook receiver, add an `additionalScrapeConfigs` block for a custom scrape target, or configure Grafana SMTP for email alerts. Document what you changed, why, and what it would do in a real environment.

**Option C — Write a ServiceMonitor**
The chart installs the `ServiceMonitor` CRD. Write a `ServiceMonitor` manifest targeting your `demo-app` service. Check the [ServiceMonitor API reference](https://prometheus-operator.dev/docs/operator/api/#monitoring.coreos.com/v1.ServiceMonitor). Even though nginx doesn't expose Prometheus metrics by default, the manifest itself demonstrates you understand how the operator pattern handles scrape configuration. Explain in your README what `/metrics` would look like if this were a real instrumented app.

**Option D — Swap in a Real Metrics App**
Replace `nginx` in your demo deployment with an app that actually exports Prometheus metrics — `prom/prometheus` itself exposes `/metrics`, as does any app built with the Prometheus client library. Wire up a ServiceMonitor, confirm the target appears in Prometheus, and build a Grafana panel for one of its metrics.

---

## Part 8: Clean Up

```bash
kubectl delete pod load-gen -n demo --ignore-not-found
helm uninstall monitoring -n monitoring
kubectl delete namespace monitoring demo
kind delete cluster --name observability
```

---

## Checkpoint

- [ ] kube-prometheus-stack installed via Helm in the `monitoring` namespace
- [ ] All monitoring pods reached Running
- [ ] Grafana accessible at `localhost:3000` — explored at least 3 pre-built dashboards
- [ ] Ran at least 2 PromQL queries in the Prometheus UI
- [ ] Found `demo-app` pods in the Grafana namespace dashboard
- [ ] Completed one extension option and committed it to your GitHub repo
- [ ] README explains what the stack does and what your extension adds

---

## Discovery Questions

1. Run `kubectl get servicemonitor -n monitoring`. How does the Prometheus Operator know which ServiceMonitors to watch? How is this different from manually editing a `prometheus.yml` scrape config?

2. The chart installed both `kube-state-metrics` and `node-exporter`. What's the difference between what each one exposes? What would you be missing without each one?

3. Open Prometheus → **Status → Configuration** and find the `scrape_configs` section. Who generated this config and where does it live in the cluster?

4. Run `kubectl get configmap -n monitoring | grep dashboard`. Pick one and inspect it with `-o yaml`. What does this tell you about managing dashboards as GitOps artifacts?

5. The `--wait` flag blocked `helm install` until all pods were ready. What exactly is Helm checking? What would happen if a pod's readiness probe never passed?

---

## Resources

- [kube-prometheus-stack (GitHub)](https://github.com/prometheus-community/helm-charts/tree/main/charts/kube-prometheus-stack)
- [Prometheus Documentation](https://prometheus.io/docs/introduction/overview/)
- [PromQL Basics](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [Grafana Documentation](https://grafana.com/docs/grafana/latest/)
- [ServiceMonitor CRD Reference](https://prometheus-operator.dev/docs/operator/api/#monitoring.coreos.com/v1.ServiceMonitor)
- [kube-state-metrics](https://github.com/kubernetes/kube-state-metrics)
