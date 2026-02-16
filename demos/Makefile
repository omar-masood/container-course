# VHS Demo Recordings for Container Course
#
# Usage:
#   make all              Record all demos (sequentially)
#   make week-01-build    Record a specific demo
#   make clean            Remove generated GIFs
#
# Prerequisites:
#   - Docker installed and running
#   - VHS installed (go install github.com/charmbracelet/vhs@latest)
#   - trivy installed (for week-02-trivy)
#   - kind cluster named "lab" running (for week-04-k8s):
#       kind create cluster --name lab
#
# Timing:
#   Sleep values in the .tape files are estimates. If a demo looks wrong
#   (commands typed over running output, or long dead pauses), adjust the
#   Sleep values in the corresponding .tape file for your machine.

ASSETS := ../assets

.PHONY: all clean setup-assets \
        week-01-build week-02-multistage week-02-trivy \
        week-03-compose week-04-k8s

all: week-01-build week-02-multistage week-02-trivy week-03-compose week-04-k8s

setup-assets:
	@mkdir -p $(ASSETS)

week-01-build: setup-assets
	vhs week-01-lab-02-docker-build.tape

week-02-multistage: setup-assets
	vhs week-02-lab-02-multistage.tape

week-02-trivy: setup-assets
	vhs week-02-lab-03-trivy-scan.tape

week-03-compose: setup-assets
	vhs week-03-lab-01-compose-up.tape

week-04-k8s: setup-assets
	vhs week-04-lab-02-k8s-deploy.tape

clean:
	rm -f $(ASSETS)/*.gif
