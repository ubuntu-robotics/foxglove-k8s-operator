# Foxglove Studio Operator (k8s)

Charmed Foxglove Studio is a charm for [Foxglove Studio](https://github.com/foxglove/studio), an integrated visualization and diagnosis tool for robotics.

## Basic Deployment

The charm is still under development and is not available yet on CharmHub.

The deployment assumes that a Juju model is deployed with microk8s.

To deploy the local charm follow these instructions:

- Clone the source repository
  
  ```
  git clone https://github.com/ubuntu-robotics/foxglove-k8s-operator.git
  ```

- Enter the folder

  ```
  cd foxglove-k8s-operator
  ```

- Build the foxglove studio charm with

  ```
  charmcraft pack
  ```

- Deploy the charm with the following command:

  ```
  juju deploy ./foxglove-studio_ubuntu-22.04-amd64.charm --resource foxglove-studio-image=ghcr.io/foxglove/studio:1.68
  ```

- Test the installation by executing the following command:

  ```
  curl -v <unit_ip>:8080
  ```

Now you can navigate to that address in your browser and visualise the foxglove studio instance. If you are running everything in a container port forwarding must be setup.


## COS lite deployment

The foxglove studio charm can be integrated with the [COS lite bundle](https://github.com/canonical/cos-lite-bundle)

An overlay is offered in this repository to ease up deployment.

To deploy with COS lite bundle follow these instructions:

- Clone the source repository

  ```
  git clone https://github.com/ubuntu-robotics/foxglove-k8s-operator.git
  ```

- Enter the folder

  ```
  cd foxglove-k8s-operator
  ```

- Build the foxglove studio charm with

  ```
  charmcraft pack
  ```

- Deploy cos-lite bundle with the robotics overlay as follows:

  ```
  juju deploy cos-lite --trust --overlay ./robotics-overlay.yaml
  ```

- The foxglove-studio charm will be available in your browser at:

  ```
  http://traefik-virtual-ip/<juju-model-name>-foxglove-studio
  ```
