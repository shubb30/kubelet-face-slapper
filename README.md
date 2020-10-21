# kubelet-face-slapper

This script and workload were created as a temporary workaround to address the problem from Kubernetes issue [87615](https://github.com/kubernetes/kubernetes/issues/87615) ([original](https://github.com/kubernetes/kubernetes/issues/87615#issuecomment-668614826)).   

You will need to build the Docker image and push it to your repository.  

Use the `daemonset.yaml` to create a DaemonSet to run on all of your Kubernetes nodes.  Modify the `image` and `imagePullSecrets` to match your repository.  
Change the namespace as needed for your environment.  
Customize the environment variables as desired for your cluster if desired.

```
NAME_SERVERS                    # comma-separated list of DNS servers for name resolution.
KUBELET_INTERVAL                # how often you want to sleep between reading logs
KUBELET_STRING_THRESHOLD        # How many instance of the check string before restarting kubelet
KUBELET_CHECK_STRING            # comma separated string of strings to check for in kubelet logs
```  

You may need to edit the tolerations if your Kubernetes setup uses different labels for control plane and etcd nodes.  This example is for Rancher/rke Kubernetes nodes.