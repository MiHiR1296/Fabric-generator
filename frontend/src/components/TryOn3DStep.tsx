import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import type { BlenderRenderJob } from '../domain/types';

type ModelKind = 'clothing' | 'furniture';

interface TryOn3DStepProps {
  renderJob: BlenderRenderJob | null;
}

function buildClothingModel(material: THREE.MeshStandardMaterial): THREE.Group {
  const group = new THREE.Group();

  const torso = new THREE.Mesh(
    new THREE.CylinderGeometry(0.85, 1.05, 2, 48, 1, true),
    material,
  );
  torso.position.y = 0.4;
  group.add(torso);

  const shoulderCap = new THREE.Mesh(new THREE.SphereGeometry(0.85, 32, 16, 0, Math.PI * 2, 0, Math.PI / 2), material);
  shoulderCap.position.y = 1.4;
  group.add(shoulderCap);

  const makeSleeve = (sign: number) => {
    const sleeve = new THREE.Mesh(
      new THREE.CylinderGeometry(0.28, 0.34, 1.6, 32, 1, true),
      material,
    );
    sleeve.rotation.z = sign * (Math.PI / 2.4);
    sleeve.position.set(sign * 1.05, 0.95, 0);
    return sleeve;
  };
  group.add(makeSleeve(1));
  group.add(makeSleeve(-1));

  const headMaterial = new THREE.MeshStandardMaterial({ color: '#d8c2a4', roughness: 0.7 });
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.42, 32, 32), headMaterial);
  head.position.y = 1.95;
  group.add(head);

  const neck = new THREE.Mesh(
    new THREE.CylinderGeometry(0.18, 0.22, 0.25, 24),
    headMaterial,
  );
  neck.position.y = 1.55;
  group.add(neck);

  return group;
}

function buildFurnitureModel(material: THREE.MeshStandardMaterial): THREE.Group {
  const group = new THREE.Group();
  const frame = new THREE.MeshStandardMaterial({ color: '#3b2f24', roughness: 0.6 });

  const seatBase = new THREE.Mesh(new THREE.BoxGeometry(3.4, 0.45, 1.4), material);
  seatBase.position.y = 0.4;
  group.add(seatBase);

  const seatCushionLeft = new THREE.Mesh(new THREE.BoxGeometry(1.55, 0.35, 1.3), material);
  seatCushionLeft.position.set(-0.8, 0.78, 0);
  group.add(seatCushionLeft);

  const seatCushionRight = new THREE.Mesh(new THREE.BoxGeometry(1.55, 0.35, 1.3), material);
  seatCushionRight.position.set(0.8, 0.78, 0);
  group.add(seatCushionRight);

  const back = new THREE.Mesh(new THREE.BoxGeometry(3.4, 1.3, 0.35), material);
  back.position.set(0, 1.1, -0.55);
  group.add(back);

  const armLeft = new THREE.Mesh(new THREE.BoxGeometry(0.35, 0.95, 1.4), material);
  armLeft.position.set(-1.7, 0.7, 0);
  group.add(armLeft);

  const armRight = new THREE.Mesh(new THREE.BoxGeometry(0.35, 0.95, 1.4), material);
  armRight.position.set(1.7, 0.7, 0);
  group.add(armRight);

  const makeLeg = (x: number, z: number) => {
    const leg = new THREE.Mesh(new THREE.BoxGeometry(0.18, 0.35, 0.18), frame);
    leg.position.set(x, 0.0, z);
    return leg;
  };
  group.add(makeLeg(-1.6, 0.55));
  group.add(makeLeg(1.6, 0.55));
  group.add(makeLeg(-1.6, -0.55));
  group.add(makeLeg(1.6, -0.55));

  return group;
}

export default function TryOn3DStep({ renderJob }: TryOn3DStepProps) {
  const [model, setModel] = useState<ModelKind>('clothing');
  const mountRef = useRef<HTMLDivElement | null>(null);
  const sceneRef = useRef<{
    scene: THREE.Scene;
    renderer: THREE.WebGLRenderer;
    camera: THREE.PerspectiveCamera;
    controls: OrbitControls;
    material: THREE.MeshStandardMaterial;
    currentModel: THREE.Group | null;
    disposeFns: Array<() => void>;
    rafId: number;
  } | null>(null);

  const fabricUrl = renderJob?.imageUrl || null;

  useEffect(() => {
    if (!mountRef.current) return undefined;

    const mount = mountRef.current;
    const width = mount.clientWidth;
    const height = mount.clientHeight;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color('#1b1b1f');

    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 100);
    camera.position.set(3.5, 2.4, 4.6);

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.setSize(width, height);
    mount.appendChild(renderer.domElement);

    const ambient = new THREE.AmbientLight(0xffffff, 0.55);
    scene.add(ambient);
    const key = new THREE.DirectionalLight(0xffffff, 1.1);
    key.position.set(4, 6, 5);
    scene.add(key);
    const rim = new THREE.DirectionalLight(0xb7c8ff, 0.4);
    rim.position.set(-4, 3, -3);
    scene.add(rim);

    const grid = new THREE.GridHelper(10, 20, 0x2c2c33, 0x2c2c33);
    grid.position.y = -0.2;
    scene.add(grid);

    const material = new THREE.MeshStandardMaterial({
      color: '#ffffff',
      roughness: 0.85,
      metalness: 0.05,
      side: THREE.DoubleSide,
    });

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.target.set(0, 0.8, 0);

    let rafId = 0;
    const animate = () => {
      controls.update();
      renderer.render(scene, camera);
      rafId = requestAnimationFrame(animate);
      sceneRef.current!.rafId = rafId;
    };

    sceneRef.current = {
      scene,
      renderer,
      camera,
      controls,
      material,
      currentModel: null,
      disposeFns: [],
      rafId: 0,
    };

    animate();

    const handleResize = () => {
      if (!mountRef.current || !sceneRef.current) return;
      const w = mountRef.current.clientWidth;
      const h = mountRef.current.clientHeight;
      sceneRef.current.renderer.setSize(w, h);
      sceneRef.current.camera.aspect = w / h;
      sceneRef.current.camera.updateProjectionMatrix();
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      if (sceneRef.current) {
        cancelAnimationFrame(sceneRef.current.rafId);
        sceneRef.current.controls.dispose();
        sceneRef.current.disposeFns.forEach((fn) => fn());
        sceneRef.current.scene.traverse((obj) => {
          if ((obj as THREE.Mesh).geometry) (obj as THREE.Mesh).geometry.dispose();
        });
        sceneRef.current.material.dispose();
        sceneRef.current.renderer.dispose();
        if (sceneRef.current.renderer.domElement.parentElement === mount) {
          mount.removeChild(sceneRef.current.renderer.domElement);
        }
        sceneRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (!sceneRef.current) return;
    const { scene, material, currentModel } = sceneRef.current;
    if (currentModel) {
      scene.remove(currentModel);
      currentModel.traverse((obj) => {
        if ((obj as THREE.Mesh).geometry) (obj as THREE.Mesh).geometry.dispose();
      });
    }
    const next = model === 'clothing' ? buildClothingModel(material) : buildFurnitureModel(material);
    scene.add(next);
    sceneRef.current.currentModel = next;
  }, [model]);

  useEffect(() => {
    if (!sceneRef.current) return;
    const { material } = sceneRef.current;

    if (!fabricUrl) {
      if (material.map) {
        material.map.dispose();
      }
      material.map = null;
      material.color.set('#7a8092');
      material.needsUpdate = true;
      return;
    }

    const loader = new THREE.TextureLoader();
    loader.setCrossOrigin('anonymous');
    loader.load(
      fabricUrl,
      (texture) => {
        texture.wrapS = THREE.RepeatWrapping;
        texture.wrapT = THREE.RepeatWrapping;
        texture.repeat.set(model === 'clothing' ? 2 : 1.5, model === 'clothing' ? 2 : 1.5);
        texture.colorSpace = THREE.SRGBColorSpace;
        texture.anisotropy = 8;
        if (material.map) {
          material.map.dispose();
        }
        material.map = texture;
        material.color.set('#ffffff');
        material.needsUpdate = true;
      },
      undefined,
      () => {
        material.color.set('#b54a4a');
        material.needsUpdate = true;
      },
    );
  }, [fabricUrl, model]);

  return (
    <section className="fabric-step-panel" data-testid="try-on-3d-step">
      <section className="card fabric-step-card">
        <div className="fabric-step-card__header">
          <div>
            <p className="eyebrow">Step 5 · Try On 3D</p>
            <h2>Wrap your fabric onto a 3D model</h2>
            <p className="fabric-step-card__summary">
              Pick a model and rotate the preview to see your generated fabric on a real surface.
            </p>
          </div>
          <div className="fabric-step-card__actions">
            <label className="field field--compact">
              <span>Model</span>
              <select
                value={model}
                onChange={(event) => setModel(event.target.value as ModelKind)}
                data-testid="try-on-3d-model-select"
              >
                <option value="clothing">Clothing (Torso)</option>
                <option value="furniture">Furniture (Sofa)</option>
              </select>
            </label>
          </div>
        </div>

        <div
          ref={mountRef}
          className="try-on-3d__viewport"
          data-testid="try-on-3d-viewport"
          style={{
            width: '100%',
            height: 480,
            borderRadius: 12,
            overflow: 'hidden',
            background: '#1b1b1f',
            border: '1px solid rgba(255, 255, 255, 0.08)',
          }}
        />

        <p className="muted">
          {fabricUrl
            ? 'Drag to orbit, scroll to zoom. The fabric texture tiles across the model surface.'
            : 'No render available yet. Run the Blender preview on Step 4 first, then come back here.'}
        </p>
      </section>
    </section>
  );
}
