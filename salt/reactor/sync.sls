sync_and_highstate:
  runner.state.orchestrate:
    - arg:
      - orchestration.startup
    - kwarg:
        pillar:
          event_data: {{ data | json() }}