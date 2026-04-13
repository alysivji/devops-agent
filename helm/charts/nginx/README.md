# nginx

Repo-owned wrapper chart for nginx. The upstream chart is the Bitnami nginx
chart from `oci://registry-1.docker.io/bitnamicharts`.

This keeps the cluster's desired state in the repo while still using the public
chart as the implementation. Local overrides live in `values.yaml` under the
dependency alias `upstream`.

Before installing from this chart, build dependencies:

```bash
helm dependency build helm/charts/nginx
```

Then deploy the repo-owned chart:

```bash
helm upgrade --install nginx helm/charts/nginx --namespace default --wait --timeout 5m
```

With the release name above, the service is `nginx-upstream` in the `default`
namespace. This chart exposes it from the machine or LAN with
`upstream.service.type: NodePort`, HTTP on node port `30080`, and HTTPS on node
port `30443`. Connect to `http://<node-ip>:30080` for HTTP.

For local access on k3s, prefer a port-forward:

```bash
kubectl port-forward svc/nginx-upstream 8080:80
curl http://127.0.0.1:8080
```

Do not use `0.0.0.0` as the curl/wget destination. If using a NodePort, connect
to a real node IP and the service's node port.
