"""
Script para crear VM ARM en Oracle Cloud Always Free
Reintenta cada 5 minutos si no hay capacidad
"""
import oci
import time
import sys
import os

# Configuración
COMPARTMENT_ID = "ocid1.tenancy.oc1..aaaaaaaayzrkgu5uhhg2gjgpfuud7rnzijdcm3mhxr24zukrb3yr3o55bzba"
SSH_PUBLIC_KEY = """ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEHNL5aqPiZXPlnXDRiZi5+DM51km5mEO3GmrvrPSn0H fredy_30@hotmail.com"""

# Imagen: Canonical Ubuntu 22.04 ARM (aarch64)
UBUNTU_IMAGE_OCID = "ocid1.image.oc1.eu-madrid-1.aaaaaaaa7rcvdaff45ybwthn46rkimr42mvzrdyfssah5rtwommnlnruna5q"

VM_NAME = "whatsapp-bot"
OCPUS = 4
MEMORY_GB = 24
BOOT_VOLUME_GB = 100

# Solo AD-1 existe para cuentas Free Tier en Madrid
AVAILABILITY_DOMAINS = [
    "JASf:EU-MADRID-1-AD-1",
]

# Probar configuraciones de menor a mayor (más probabilidad de cupo)
SHAPE_CONFIGS = [
    (2, 12),   # 2 OCPU, 12 GB
    (4, 24),   # 4 OCPU, 24 GB
]

def get_or_create_vcn_subnet(compute_client, network_client):
    """Busca VCN existente o crea uno nuevo"""
    print("Buscando VCN existente...")

    # Buscar VCNs existentes
    vcns = network_client.list_vcns(
        compartment_id=COMPARTMENT_ID,
        display_name="vcn-whatsapp"
    ).data

    if vcns:
        vcn = vcns[0]
        print(f"  VCN encontrado: {vcn.display_name} ({vcn.id})")
    else:
        print("  Creando VCN nuevo...")
        vcn = network_client.create_vcn(
            oci.core.models.CreateVcnDetails(
                compartment_id=COMPARTMENT_ID,
                display_name="vcn-whatsapp",
                cidr_block="10.0.0.0/16",
                dns_label="vcnwhatsapp"
            )
        ).data
        print(f"  VCN creado: {vcn.id}")

    # Buscar subnet existente
    subnets = network_client.list_subnets(
        compartment_id=COMPARTMENT_ID,
        display_name="subnet-whatsapp",
        vcn_id=vcn.id
    ).data

    if subnets:
        subnet = subnets[0]
        print(f"  Subnet encontrada: {subnet.display_name} ({subnet.id})")
    else:
        print("  Creando subnet pública...")
        subnet = network_client.create_subnet(
            oci.core.models.CreateSubnetDetails(
                compartment_id=COMPARTMENT_ID,
                display_name="subnet-whatsapp",
                vcn_id=vcn.id,
                cidr_block="10.0.1.0/24",
                dns_label="subwhatsapp",
                prohibit_public_ip_on_vnic=False
            )
        ).data
        print(f"  Subnet creada: {subnet.id}")

    # Crear Internet Gateway si no existe
    igs = network_client.list_internet_gateways(
        compartment_id=COMPARTMENT_ID,
        vcn_id=vcn.id
    ).data

    if not igs:
        print("  Creando Internet Gateway...")
        ig = network_client.create_internet_gateway(
            oci.core.models.CreateInternetGatewayDetails(
                compartment_id=COMPARTMENT_ID,
                vcn_id=vcn.id,
                display_name="ig-whatsapp",
                is_enabled=True
            )
        ).data
        print(f"  Internet Gateway creado: {ig.id}")

    # Buscar route table y agregar ruta a Internet Gateway
    route_tables = network_client.list_route_tables(
        compartment_id=COMPARTMENT_ID,
        vcn_id=vcn.id
    ).data

    if route_tables:
        rt = route_tables[0]
        has_internet_route = any(
            r.cidr_block == "0.0.0.0/0" for r in rt.route_rules
        )
        if not has_internet_route and igs:
            print("  Agregando ruta a Internet...")
            ig = igs[0] if isinstance(igs, list) else network_client.list_internet_gateways(
                compartment_id=COMPARTMENT_ID, vcn_id=vcn.id
            ).data[0]

            route_rules = list(rt.route_rules)
            route_rules.append(
                oci.core.models.RouteRule(
                    network_entity_id=ig.id,
                    cidr_block="0.0.0.0/0",
                    destination="0.0.0.0/0",
                    destination_type="CIDR_BLOCK"
                )
            )
            network_client.update_route_table(
                rt.id,
                oci.core.models.UpdateRouteTableDetails(route_rules=route_rules)
            )
            print("  Ruta a Internet agregada")

    return vcn.id, subnet.id, COMPARTMENT_ID


def open_firewall(network_client):
    """Abre puertos en el security list por defecto"""
    print("Configurando firewall...")

    security_lists = network_client.list_security_lists(
        compartment_id=COMPARTMENT_ID
    ).data

    for sl in security_lists:
        needs_update = False
        ingress_rules = list(sl.ingress_security_rules)

        # Puertos que necesitamos abiertos
        ports_to_open = [
            (22, "SSH"),
            (80, "HTTP"),
            (443, "HTTPS"),
            (3000, "Bot-Web"),
            (8080, "Evolution-API"),
        ]

        existing_ports = set()
        for r in ingress_rules:
            if r.protocol == "6" and r.tcp_options and r.tcp_options.destination_port_range:
                port_range = r.tcp_options.destination_port_range
                existing_ports.add(port_range.min)
                existing_ports.add(port_range.max)

        for port, name in ports_to_open:
            if port not in existing_ports:
                print(f"  Abriendo puerto {port} ({name})...")
                ingress_rules.append(
                    oci.core.models.IngressSecurityRule(
                        protocol="6",
                        source="0.0.0.0/0",
                        tcp_options=oci.core.models.TcpOptions(
                            destination_port_range=[
                                oci.core.models.PortRange(min=port, max=port)
                            ]
                        ),
                        description=name
                    )
                )
                needs_update = True

        if needs_update:
            network_client.update_security_list(
                sl.id,
                oci.core.models.UpdateSecurityListDetails(
                    ingress_security_rules=ingress_rules
                )
            )
            print("  Firewall actualizado")
            return


def create_instance(compute_client, subnet_id, ad, ocpus, memory_gb):
    """Intenta crear la instancia en un dominio de disponibilidad"""
    print(f"\nIntentando crear VM en {ad}...")
    print(f"  Shape: VM.Standard.A1.Flex, {ocpus} OCPU, {memory_gb} GB RAM")

    try:
        instance = compute_client.launch_instance(
            oci.core.models.LaunchInstanceDetails(
                compartment_id=COMPARTMENT_ID,
                display_name=VM_NAME,
                availability_domain=ad,
                shape="VM.Standard.A1.Flex",
                shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(
                    ocpus=ocpus,
                    memory_in_gbs=memory_gb
                ),
                source_details=oci.core.models.InstanceSourceViaImageDetails(
                    source_type="image",
                    image_id=UBUNTU_IMAGE_OCID,
                    boot_volume_size_in_gbs=BOOT_VOLUME_GB
                ),
                create_vnic_details=oci.core.models.CreateVnicDetails(
                    subnet_id=subnet_id,
                    assign_public_ip=True,
                    display_name="vnic-whatsapp"
                ),
                metadata={
                    "ssh_authorized_keys": SSH_PUBLIC_KEY
                }
            )
        ).data

        print(f"\n=== VM CREADA EXITOSAMENTE ===")
        print(f"   ID: {instance.id}")
        print(f"   Estado: {instance.lifecycle_state}")

        # Obtener IP pública
        vnic_attachments = compute_client.list_vnic_attachments(
            compartment_id=COMPARTMENT_ID,
            instance_id=instance.id
        ).data

        if vnic_attachments:
            vnic = compute_client.get_vnic(vnic_attachments[0].vnic_id).data
            print(f"   IP Pública: {vnic.public_ip}")
            print(f"   IP Privada: {vnic.private_ip}")

        return instance

    except oci.exceptions.ServiceError as e:
        if e.code == "LimitExceeded" or "capacity" in str(e).lower():
            print(f"  [!] Sin capacidad en {ad}: {e.message[:100]}")
            return None
        elif e.code == "InvalidParameter" and "subnet" in str(e).lower():
            print(f"  [X] Error de subnet: {e.message[:100]}")
            return "SUBNET_ERROR"
        else:
            print(f"  [X] Error: {e.code} - {e.message[:200]}")
            return None
    except Exception as e:
        print(f"  [X] Error inesperado: {e}")
        return None


def run_setup_script(public_ip):
    """Genera comando para ejecutar setup en la VM"""
    print(f"\n[+] Para configurar la VM, ejecuta en otra terminal:")
    print(f"   ssh -i ~/.oci/oci_api_key.pem ubuntu@{public_ip}")
    print(f"\n   Luego dentro de la VM:")
    print(f"   curl -sL https://raw.githubusercontent.com/fredy30-Rojas/proyectos-ia/master/oracle-cloud/scripts/setup-vm.sh | bash")


def main():
    print("=" * 60)
    print("  CREADOR DE VM ORACLE CLOUD - WHATSAPP BOT")
    print("  Reintenta cada 5 min si no hay capacidad")
    print("=" * 60)

    # Configurar cliente OCI
    config = oci.config.from_file()
    compute_client = oci.core.ComputeClient(config)
    network_client = oci.core.VirtualNetworkClient(config)
    identity_client = oci.identity.IdentityClient(config)

    # Verificar compartimento
    print(f"\nCompartimento: {COMPARTMENT_ID}")

    # Preparar red
    vcn_id, subnet_id, _ = get_or_create_vcn_subnet(compute_client, network_client)
    # Firewall se configura después via SSH

    # Intentar crear VM
    attempt = 0

    while True:
        attempt += 1

        for ad in AVAILABILITY_DOMAINS:
            for ocpus, memory_gb in SHAPE_CONFIGS:
                print(f"\n{'='*40}")
                print(f"Intento #{attempt} - {ad} ({ocpus} CPU, {memory_gb} GB)")
                print(f"Hora: {time.strftime('%Y-%m-%d %H:%M:%S')}")

                result = create_instance(compute_client, subnet_id, ad, ocpus, memory_gb)

                if result == "SUBNET_ERROR":
                    print("Error de subnet - recreando red...")
                    vcn_id, subnet_id, _ = get_or_create_vcn_subnet(compute_client, network_client)
                    continue

                if result:
                    # Éxito
                    print("\n" + "=" * 60)
                    print("  *** VM CREADA! El bot de WhatsApp estara listo pronto ***")
                    print("=" * 60)

                    # Obtener IP pública
                    vnic_attachments = compute_client.list_vnic_attachments(
                        compartment_id=COMPARTMENT_ID,
                        instance_id=result.id
                    ).data
                    if vnic_attachments:
                        vnic = network_client.get_vnic(vnic_attachments[0].vnic_id).data
                        print(f"\n[IP] IP Publica: {vnic.public_ip}")
                        print(f"[SSH] ssh -i C:/Users/Fredy/.oci/oci_api_key.pem ubuntu@{vnic.public_ip}")

                    return

                # Esperar entre intentos para evitar rate limiting
                time.sleep(5)

        # Esperar antes de reintentar
        wait_minutes = 10
        print(f"\n[!] Sin capacidad. Reintentando en {wait_minutes} minutos...")
        print(f"   (Ctrl+C para cancelar)")

        try:
            time.sleep(wait_minutes * 60)
        except KeyboardInterrupt:
            print("\n\nCancelado por el usuario.")
            break


if __name__ == "__main__":
    main()
