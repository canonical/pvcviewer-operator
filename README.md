# PVCViewer operator!

The Charmed PVC Viewer operator for Juju deploys the upstream's [PVC Viewer Controller](https://github.com/kubeflow/kubeflow/tree/master/components/pvcviewer-controller). Using this component, PVCViewers can easily be created. PVCViewers enable users to open a filebrowser on arbitrary persistent volume claims, letting them inspect, download, upload and manipulate data.

## Description

The component is meant to be used in interaction with other components, such as the volumes web app. These are to create an instance of the custom resource.
The controller will then generate deployments, services and virtualservices base on the spec.

A resource starting a filebrowser might look like this:

```yaml
apiVersion: kubeflow.org/v1alpha1
kind: PVCViewer
metadata:
  name: pvcviewer-sample
  namespace: kubeflow-user-example-com
spec:
  # The PVC we are watching
  pvc: pvcviewer-sample
  # The podSpec is applied to the deployment.Spec.Template.Spec
  # and thus, represents the core viewer's application
  # Gets set to a default PodSpec, if not specified
  # podSpec: {}
  # If defined, the viewer will be exposed via a Service and a VirtualService
  networking:
    # Specifies the application's target port used by the Service
    targetPort: 8080
    # The base prefix is suffixed by '/namespace/name' to create the
    # VirtualService's prefix and a unique URL for each started viewer
    basePrefix: "/pvcviewer"
    # You may specify the VirtualService's rewrite.
    # If not set, the prefix's value is used
    rewrite: "/"
    # By default, no timeout is set
    # timeout: 30s
  # If set to true, the controller detects RWO-Volumes referred to by the
  # podSpec and uses affinities to schedule the viewer to nodes
  # where the volume is currently mounted. This enables the viewer to
  # access RWO-Volumes, even though they might already be mounted.
  rwoScheduling: true
```

## Usage

The Charmed PVC Viewer Operator can be deployed using the Juju command line as
follows

```sh
$ juju deploy pvcviewer-controller
```

Please check the Charmhub page for latest versions https://charmhub.io/pvcviewer-operator.

## Looking for a fully supported platform for MLOps?

Canonical [Charmed Kubeflow](https://charmed-kubeflow.io) is a state of the art, fully supported MLOps platform that helps data scientists collaborate on AI innovation on any cloud from concept to production, offered by Canonical - the publishers of [Ubuntu](https://ubuntu.com).

[![Kubeflow diagram](https://res.cloudinary.com/canonical/image/fetch/f_auto,q_auto,fl_sanitize,w_350,h_304/https://assets.ubuntu.com/v1/10400c98-Charmed-kubeflow-Topology-header.svg)](https://charmed-kubeflow.io)


Charmed Kubeflow is free to use: the solution can be deployed in any environment without constraints, paywall or restricted features. Data labs and MLOps teams only need to train their data scientists and engineers once to work consistently and efficiently on any cloud – or on-premise.

Charmed Kubeflow offers a centralised, browser-based MLOps platform that runs on any conformant Kubernetes – offering enhanced productivity, improved governance and reducing the risks associated with shadow IT.

Learn more about deploying and using Charmed Kubeflow at [https://charmed-kubeflow.io](https://charmed-kubeflow.io).

### Documentation
Please see the [official docs site](https://charmed-kubeflow.io/docs) for complete documentation of the Charmed Kubeflow distribution.

### Bugs and feature requests
If you find a bug in our operator or want to request a specific feature, please file a bug here: 
[https://github.com/canonical/seldon-core-operator/issues](https://github.com/canonical/seldon-core-operator/issues)

### License
Charmed Kubeflow is free software, distributed under the [Apache Software License, version 2.0](https://github.com/canonical/seldon-core-operator/blob/master/LICENSE).


### Contributing
Canonical welcomes contributions to Charmed Kubeflow. Please check out our [contributor agreement](https://ubuntu.com/legal/contributors) if you're interested in contributing to the distribution.

### Security
Security issues in Charmed Kubeflow can be reported through [LaunchPad](https://wiki.ubuntu.com/DebuggingSecurity#How%20to%20File). Please do not file GitHub issues about security issues.
