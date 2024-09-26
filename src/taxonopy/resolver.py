from taxonopy.container_handler import ContainerHandler

def resolve_names(input_file, output_file, exec_method='docker'):
    if exec_method == 'docker':
        handler = ContainerHandler()
        if handler.is_docker_available():
            handler.run_container(input_file, output_file)
        else:
            raise RuntimeError("Docker is not available on this system.")
    else:
        raise ValueError(f"Execution method '{exec_method}' is not yet implemented.")
