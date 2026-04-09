 1 #!/bin/bash
      echo "Setting up Satellite Simulator..."
      python3 -m venv venv
      source venv/bin/activate
      pip install -r simulator/requirements.txt
      curl -o simulator/oneweb_satellites.json 
       "https://celestrak.org/NORAD/elements/gp.php?GROUP=oneweb&FORMAT=JSON"
      chmod +x simulator/*.sh
      echo "Setup complete! Run 'cd simulator && bash bootstrapperCustomInput.sh'"