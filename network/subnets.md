# Subnet Allocation and Stateless Network Access Control (NACL)

## 1. Subnet Allocation

### Requirements and Network Specification
- **Assigned CIDR Block**: `10.20.0.0/16` (Total: 65,536 IP addresses)
- **Allocation Strategy**: Largest host requirement to smallest host requirement, starting at `10.20.0.0`, packing each subnet contiguously without gaps.
- **Usable Host Formula**: $\text{Usable Hosts} = 2^{32 - \text{prefix}} - 2$ (subtracting network address and directed broadcast address).

### Calculations

1. **Subnet: `app`**
   - **Required Hosts**: 1,000
   - **Host Bits ($h$) Calculation**: $2^h - 2 \ge 1000 \implies h = 10$ ($2^{10} - 2 = 1,022 \ge 1000$).
   - **Prefix Length**: $32 - 10 = /22$ (Subnet Mask: `255.255.252.0`).
   - **Total IP Addresses**: $2^{10} = 1,024$.
   - **Base Network**: `10.20.0.0/22`.
   - **Usable Range**: `10.20.0.1` to `10.20.3.254`.
   - **Broadcast Address**: `10.20.3.255`.
   - **Number of Usable Hosts**: 1,022.

2. **Subnet: `public`**
   - **Required Hosts**: 250
   - **Host Bits ($h$) Calculation**: $2^h - 2 \ge 250 \implies h = 8$ ($2^8 - 2 = 254 \ge 250$).
   - **Prefix Length**: $32 - 8 = /24$ (Subnet Mask: `255.255.255.0`).
   - **Total IP Addresses**: $2^8 = 256$.
   - **Base Network**: Next contiguous address is `10.20.4.0/24`.
   - **Usable Range**: `10.20.4.1` to `10.20.4.254`.
   - **Broadcast Address**: `10.20.4.255`.
   - **Number of Usable Hosts**: 254.

3. **Subnet: `data`**
   - **Required Hosts**: 100
   - **Host Bits ($h$) Calculation**: $2^h - 2 \ge 100 \implies h = 7$ ($2^7 - 2 = 126 \ge 100$).
   - **Prefix Length**: $32 - 7 = /25$ (Subnet Mask: `255.255.255.128`).
   - **Total IP Addresses**: $2^7 = 128$.
   - **Base Network**: Next contiguous address is `10.20.5.0/25`.
   - **Usable Range**: `10.20.5.1` to `10.20.5.126`.
   - **Broadcast Address**: `10.20.5.127`.
   - **Number of Usable Hosts**: 126.

4. **Subnet: `management`**
   - **Required Hosts**: 20
   - **Host Bits ($h$) Calculation**: $2^h - 2 \ge 20 \implies h = 5$ ($2^5 - 2 = 30 \ge 20$).
   - **Prefix Length**: $32 - 5 = /27$ (Subnet Mask: `255.255.255.224`).
   - **Total IP Addresses**: $2^5 = 32$.
   - **Base Network**: Next contiguous address is `10.20.5.128/27`.
   - **Usable Range**: `10.20.5.129` to `10.20.5.158`.
   - **Broadcast Address**: `10.20.5.159`.
   - **Number of Usable Hosts**: 30.

*(Remaining unallocated address space in block: `10.20.5.160` to `10.20.255.255`).*

---

### Subnet Allocation Table

| Subnet | Hosts Needed | Network Address | Prefix Length | Usable Host Range | Broadcast Address | Number of Usable Hosts |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **app** | 1,000 | `10.20.0.0` | `/22` | `10.20.0.1` – `10.20.3.254` | `10.20.3.255` | 1,022 |
| **public** | 250 | `10.20.4.0` | `/24` | `10.20.4.1` – `10.20.4.254` | `10.20.4.255` | 254 |
| **data** | 100 | `10.20.5.0` | `/25` | `10.20.5.1` – `10.20.5.126` | `10.20.5.127` | 126 |
| **management** | 20 | `10.20.5.128` | `/27` | `10.20.5.129` – `10.20.5.158` | `10.20.5.159` | 30 |

---

## 2. Stateless NACL Reasoning & Analysis

### Why a Stateless NACL Needs Separate Rules for Reply Traffic
Unlike stateful firewalls (such as Linux `iptables` with `conntrack` or AWS Security Groups), a Network Access Control List (NACL) is **stateless**. This means it does not maintain a connection tracking table and evaluates each packet in isolation without awareness of prior handshakes or ongoing sessions:
1. When an inbound request arrives from a client (e.g., TCP SYN arriving at port 443 with a source ephemeral port such as 51234), the inbound rule permits the packet.
2. However, when the server generates a response packet (TCP SYN-ACK / ACK / Data), that response is transmitted outbound from source port 443 towards the client's destination port 51234.
3. Because the NACL cannot remember that this outbound packet corresponds to an authorized incoming request, the outbound filtering engine would drop it unless an explicit outbound rule allows traffic to destination ephemeral ports (`1024-65535`).
4. Similarly, when the load balancer makes an outbound request to the backend microservice (`TCP 8000` on `10.20.0.0/22`), the response coming back from the backend application enters the public subnet as inbound traffic targeting the load balancer's ephemeral port. Hence, an explicit inbound rule allowing traffic from `10.20.0.0/22` on destination ports `1024-65535` is strictly required.

### Why Rule Ordering Matters for `198.51.100.0/24`
NACL rules are processed sequentially in ascending numerical order (**lowest rule number first**), and the evaluation is **first-match-wins**:
1. If a packet matches a rule, the designated action (`allow` or `deny`) is applied immediately, and subsequent rules are ignored.
2. If the general web traffic allow rules (e.g., Allow TCP 80 and 443 from `0.0.0.0/0`) were placed at rule numbers lower than the block rule (for instance, allow rules at 100 and block rule at 200), an incoming HTTP/HTTPS packet from the abusive range `198.51.100.0/24` would match `0.0.0.0/0` first and be permitted.
3. Therefore, the explicit deny rule for `198.51.100.0/24` must have a lower rule number (Rule 100) than the broad allow rules (Rules 110 and 120). When a packet from `198.51.100.0/24` arrives, Rule 100 matches first and immediately drops it, guaranteeing that malicious traffic is blocked regardless of the destination port.

