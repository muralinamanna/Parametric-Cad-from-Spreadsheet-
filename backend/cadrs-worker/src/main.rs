use cadrs_kernel::{
    BodyId, BoolOp, ChamferSpec, Curve2, CurveKind, DefaultKernel, Extent, Kernel, Loop, OpResult,
    Plane, Primitive, Profile, Region, Tessellation, TriMesh,
};
use nalgebra::{Point2, Point3, Vector3};
use serde::Deserialize;
use serde_json::{Value, json};
use std::{
    fs,
    io::{self, Write},
    path::Path,
};

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

#[derive(Deserialize)]
struct Job {
    size: [f64; 3],
    slots: Vec<[f64; 4]>,
    features: Vec<Feature>,
}

#[derive(Deserialize)]
struct Feature {
    id: String,
    #[serde(flatten)]
    operation: Operation,
}

#[derive(Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
enum Operation {
    Holes {
        centers: Vec<[f64; 2]>,
        diameter: f64,
    },
    Pocket {
        x: f64,
        y: f64,
        width: f64,
        length: f64,
        depth: f64,
    },
    Chamfer {
        edge: String,
        size: f64,
    },
    Fillet {
        edge: String,
        size: f64,
    },
}

fn rectangle([x, y, width, length]: [f64; 4], inner: bool) -> Loop {
    let mut corners = [
        Point2::new(x, y),
        Point2::new(x + width, y),
        Point2::new(x + width, y + length),
        Point2::new(x, y + length),
    ];
    if inner {
        corners.reverse();
    }
    Loop {
        curves: (0..4)
            .map(|i| Curve2::Line {
                a: corners[i],
                b: corners[(i + 1) % 4],
                source: None,
            })
            .collect(),
    }
}

fn single(result: OpResult) -> Result<BodyId> {
    match result.bodies.as_slice() {
        [body] => Ok(*body),
        _ => Err("The operation must leave exactly one solid.".into()),
    }
}

fn outer_edge(
    k: &DefaultKernel,
    body: BodyId,
    edge: &str,
    [w, l, t]: [f64; 3],
) -> Result<cadrs_kernel::EdgeId> {
    let (a, b) = match edge {
        "top-front" => (Point3::new(0., 0., t), Point3::new(w, 0., t)),
        "top-back" => (Point3::new(0., l, t), Point3::new(w, l, t)),
        "top-left" => (Point3::new(0., 0., t), Point3::new(0., l, t)),
        "top-right" => (Point3::new(w, 0., t), Point3::new(w, l, t)),
        _ => return Err("Unknown plate edge. Select a top outside edge again.".into()),
    };
    let near = |left: Point3<f64>, right: Point3<f64>| (left - right).norm() <= 1e-6;
    let matches: Vec<_> = k
        .edges(body)?
        .into_iter()
        .filter(|e| {
            e.curve == CurveKind::Line
                && ((near(e.start, a) && near(e.end, b)) || (near(e.start, b) && near(e.end, a)))
        })
        .collect();
    match matches.as_slice(){
        [edge] => Ok(edge.id),
        _ => Err("The selected top edge was changed or split by an earlier feature. Select another edge or reorder the features.".into()),
    }
}

fn check_removed(k: &DefaultKernel, before: BodyId, after: BodyId, expected: f64) -> Result<()> {
    let removed = k.mass_properties(before)?.volume - k.mass_properties(after)?.volume;
    if (removed - expected).abs() > 1e-5f64.max(expected * 1e-7) {
        return Err(
            "The opening overlaps an existing slot or feature. Move it to clear material.".into(),
        );
    }
    Ok(())
}

fn apply(
    k: &mut DefaultKernel,
    body: BodyId,
    size: [f64; 3],
    feature: Operation,
) -> Result<BodyId> {
    let thickness = size[2];
    let over = 0.1;
    let result = match feature {
        Operation::Holes { centers, diameter } => {
            let mut current = body;
            for [x, y] in centers {
                let tool = single(k.primitive(&Primitive::cylinder(
                    Point3::new(x, y, -over),
                    Vector3::z(),
                    diameter / 2.,
                    thickness + 2. * over,
                ))?)?;
                let next = single(k.boolean(BoolOp::Subtract, current, &[tool])?)?;
                check_removed(
                    k,
                    current,
                    next,
                    std::f64::consts::PI * (diameter / 2.).powi(2) * thickness,
                )?;
                current = next;
            }
            current
        }
        Operation::Pocket {
            x,
            y,
            width,
            length,
            depth,
        } => {
            let tool = single(k.primitive(&Primitive::block(
                Point3::new(x, y, thickness - depth),
                Point3::new(x + width, y + length, thickness + over),
            ))?)?;
            let next = single(k.boolean(BoolOp::Subtract, body, &[tool])?)?;
            check_removed(k, body, next, width * length * depth)?;
            next
        }
        Operation::Chamfer {
            edge,
            size: distance,
        } => {
            let id = outer_edge(k, body, &edge, size)?;
            single(k.chamfer(body, &[id], ChamferSpec::EqualDistance(distance))?)?
        }
        Operation::Fillet { edge, size: radius } => {
            let id = outer_edge(k, body, &edge, size)?;
            single(k.fillet(body, &[id], radius)?)?
        }
    };
    if k.mass_properties(result)?.volume >= k.mass_properties(body)?.volume - 1e-8 {
        return Err("The feature did not remove material. Check its position or its size.".into());
    }
    Ok(result)
}

fn write_stl(path: &Path, mesh: TriMesh) -> Result<()> {
    let mut file = io::BufWriter::new(fs::File::create(path)?);
    file.write_all(&[0; 80])?;
    file.write_all(&u32::try_from(mesh.indices.len())?.to_le_bytes())?;
    for indices in mesh.indices {
        let [a, b, c] = indices.map(|i| mesh.positions[i as usize]);
        let normal = (b - a)
            .cross(&(c - a))
            .try_normalize(1e-16)
            .unwrap_or(Vector3::zeros());
        for v in [normal, a.coords, b.coords, c.coords] {
            for coord in v.iter() {
                file.write_all(&(*coord as f32).to_le_bytes())?;
            }
        }
        file.write_all(&0u16.to_le_bytes())?;
    }
    file.flush()?;
    Ok(())
}

fn build(path: &Path) -> Result<Value> {
    let job: Job = serde_json::from_slice(&fs::read(path.join("job.json"))?)?;
    let [w, l, t] = job.size;
    let profile = Profile::new(
        Plane::top(),
        vec![Region {
            outer: rectangle([0., 0., w, l], false),
            holes: job
                .slots
                .into_iter()
                .map(|slot| rectangle(slot, true))
                .collect(),
            source: None,
        }],
    );
    let mut k = DefaultKernel::new();
    let mut body = single(k.extrude(&profile, Extent::Blind(t))?)?;
    for f in job.features {
        body = match apply(&mut k, body, job.size, f.operation) {
            Ok(next) => next,
            Err(error) => return Ok(json!({"error":error.to_string(),"feature":f.id})),
        };
    }
    let mesh = k.tessellate(body, Tessellation::default())?;
    if mesh.indices.is_empty() {
        return Err("The solid produced no display triangles.".into());
    }
    write_stl(&path.join("detailed.stl"), mesh)?;
    fs::write(path.join("detailed.step"), k.export_step(&[body])?)?;
    let bounds = k.bounding_box(body)?;
    Ok(
        json!({"volume":k.mass_properties(body)?.volume,"bounds":{"min":bounds.min,"max":bounds.max}}),
    )
}

fn main() -> Result<()> {
    let folder = std::env::args_os()
        .nth(1)
        .ok_or("Expected a job directory.")?;
    let path = Path::new(&folder);
    let outcome = build(path).unwrap_or_else(|error| json!({"error":error.to_string()}));
    fs::write(path.join("result.json"), serde_json::to_vec(&outcome)?)?;
    Ok(())
}
